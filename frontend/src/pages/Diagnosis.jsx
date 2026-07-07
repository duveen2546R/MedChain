import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import ConsoleShell from "../components/ConsoleShell";
import Icon from "../components/Icon";
import { ApiError, apiJson } from "../lib/api";
import { useAuth } from "../lib/auth";

// Built-in breast-cancer schema (legacy objective with no uploaded validation CSV).
const BUILTIN_FEATURES = [
  "mean radius", "mean texture", "mean perimeter", "mean area", "mean smoothness",
  "mean compactness", "mean concavity", "mean concave points", "mean symmetry",
  "mean fractal dimension", "radius error", "texture error", "perimeter error",
  "area error", "smoothness error", "compactness error", "concavity error",
  "concave points error", "symmetry error", "fractal dimension error", "worst radius",
  "worst texture", "worst perimeter", "worst area", "worst smoothness",
  "worst compactness", "worst concavity", "worst concave points", "worst symmetry",
  "worst fractal dimension",
];
const BUILTIN_POSITIVE = "benign";
const SAMPLE_CASES = {
  suspicious: [11.42, 20.38, 77.58, 386.1, 0.1425, 0.2839, 0.2414, 0.1052, 0.2597, 0.0974, 0.4956, 1.156, 3.445, 27.23, 0.0091, 0.0746, 0.0566, 0.0187, 0.0596, 0.0092, 14.91, 26.5, 98.87, 567.7, 0.2098, 0.8663, 0.6869, 0.2575, 0.6638, 0.173],
  routine: [12.05, 14.63, 78.04, 449.3, 0.1031, 0.0909, 0.0659, 0.0275, 0.1675, 0.0604, 0.2636, 0.7294, 1.848, 19.87, 0.0055, 0.0143, 0.0232, 0.0057, 0.0143, 0.0024, 13.76, 20.7, 89.88, 582.6, 0.1494, 0.2156, 0.305, 0.0655, 0.2747, 0.083],
};

const TIER_COPY = {
  high: { label: "High confidence", cls: "is-ok" },
  moderate: { label: "Moderate confidence", cls: "is-mid" },
  low: { label: "Low confidence", cls: "is-warn" },
};

export default function Diagnosis() {
  const { user, token } = useAuth();
  const mayPredict = ["clinic_user", "platform_admin"].includes(user?.role);

  const [objectives, setObjectives] = useState([]);
  const [objectiveId, setObjectiveId] = useState(""); // "" == built-in breast-cancer
  const [schema, setSchema] = useState(null); // per-objective schema, or null for built-in
  const [features, setFeatures] = useState(BUILTIN_FEATURES.map(() => ""));
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const featureNames = schema ? schema.feature_columns : BUILTIN_FEATURES;
  const positiveLabel = schema ? schema.positive_label : BUILTIN_POSITIVE;

  useEffect(() => {
    if (!mayPredict || !token) return;
    (async () => {
      try {
        const list = await apiJson("/training-objectives", {}, token);
        setObjectives(list.filter((o) => o.has_schema));
      } catch {
        /* objectives are optional; the built-in model still works */
      }
    })();
  }, [mayPredict, token]);

  // Load the selected objective's schema (or reset to the built-in form).
  useEffect(() => {
    setResult(null);
    setError("");
    if (!objectiveId) {
      setSchema(null);
      setFeatures(BUILTIN_FEATURES.map(() => ""));
      return;
    }
    (async () => {
      try {
        const s = await apiJson(`/training-objectives/${objectiveId}/schema`, {}, token);
        setSchema(s);
        setFeatures(s.feature_columns.map(() => ""));
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Could not load this objective's schema.");
      }
    })();
  }, [objectiveId, token]);

  function loadSample(key) {
    setFeatures(SAMPLE_CASES[key].map(String));
    setResult(null);
    setError("");
  }

  function setFeature(index, value) {
    setFeatures((prev) => prev.map((v, i) => (i === index ? value : v)));
  }

  async function onPredict(e) {
    e.preventDefault();
    setError("");
    const parsed = features.map((v) => Number(v));
    if (parsed.length === 0 || parsed.some((v) => !Number.isFinite(v))) {
      setError("Every measurement must be a number.");
      return;
    }
    setBusy(true);
    try {
      const body = objectiveId ? { features: parsed, objective_id: objectiveId } : { features: parsed };
      setResult(await apiJson("/inference/predict", { method: "POST", body: JSON.stringify(body) }, token));
    } catch (err) {
      setResult(null);
      setError(err instanceof ApiError ? err.message : "Prediction failed. Try again.");
    } finally {
      setBusy(false);
    }
  }

  const tier = result ? TIER_COPY[result.confidence_tier] || TIER_COPY.low : null;
  const caption = useMemo(
    () => (schema ? `${featureNames.length} features · ${schema.target_column}` : "30 features from a fine-needle aspirate image"),
    [schema, featureNames.length]
  );

  return (
    <ConsoleShell
      here="Diagnosis"
      title="Federated"
      titleEm="Diagnosis"
      caption="Run a real prediction from the current aggregated global model. Measurements are analyzed in memory and never stored or logged."
    >
      {!mayPredict ? (
        <div className="panel diag__deny">
          <Icon name="lock" size={18} />
          <div>
            <b>Inference is limited to clinic accounts.</b>
            <p>Hospital, auditor, and research roles interact with training and audit sections instead. Sign in with a clinic account to run predictions.</p>
          </div>
        </div>
      ) : (
        <div className="diag">
          <motion.section
            className="panel diag__form"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.16, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="panel__head">
              <div>
                <h3>Case measurements</h3>
                <span className="panel__caption">{caption}</span>
              </div>
              {!schema && (
                <div className="diag__samples">
                  <button type="button" className="diag__sample" onClick={() => loadSample("routine")}>
                    <Icon name="patient" size={13} /> Routine profile
                  </button>
                  <button type="button" className="diag__sample" onClick={() => loadSample("suspicious")}>
                    <Icon name="search" size={13} /> Suspicious profile
                  </button>
                </div>
              )}
            </div>

            <label className="diag__field diag__objective">
              <span>Model</span>
              <select value={objectiveId} onChange={(e) => setObjectiveId(e.target.value)}>
                <option value="">Breast cancer (built-in)</option>
                {objectives.map((o) => (
                  <option key={o.id} value={o.id}>{o.name}</option>
                ))}
              </select>
            </label>

            <form onSubmit={onPredict}>
              <div className="diag__grid">
                {featureNames.map((name, index) => (
                  <label key={name} className="diag__field">
                    <span>{name}</span>
                    <input
                      type="number"
                      step="any"
                      value={features[index] ?? ""}
                      onChange={(e) => setFeature(index, e.target.value)}
                      required
                    />
                  </label>
                ))}
              </div>
              {error && <p className="diag__error">{error}</p>}
              <motion.button
                whileTap={{ scale: 0.97 }}
                type="submit"
                className="btn btn-primary diag__submit"
                disabled={busy}
              >
                {busy ? "Analyzing…" : "Run prediction"}
                {!busy && <Icon name="arrow" size={16} />}
              </motion.button>
            </form>
          </motion.section>

          <motion.section
            className="panel diag__result"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.24, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="panel__head">
              <div>
                <h3>Model assessment</h3>
                <span className="panel__caption">From the federated global model</span>
              </div>
              {result && <span className="panel__tag">{result.model_version}</span>}
            </div>

            {!result ? (
              <div className="diag__placeholder">
                <Icon name="brain" size={26} />
                <p>Pick a model, enter measurements, then run a prediction. The assessment comes from the model your consortium trained together.</p>
              </div>
            ) : (
              <div className="diag__outcome">
                <span className={`diag__verdict ${result.prediction === positiveLabel ? "is-benign" : "is-malignant"}`}>
                  {result.prediction}
                </span>
                <div className="diag__probs">
                  <div className="diag__prob">
                    <span>P({positiveLabel})</span>
                    <div className="bar"><motion.i animate={{ width: `${result.probability * 100}%` }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }} /></div>
                    <b className="tnum">{(result.probability * 100).toFixed(1)}%</b>
                  </div>
                  <div className="diag__prob">
                    <span>Confidence</span>
                    <div className="bar"><motion.i animate={{ width: `${result.confidence * 100}%` }} transition={{ duration: 0.8, ease: [0.22, 1, 0.36, 1] }} /></div>
                    <b className="tnum">{(result.confidence * 100).toFixed(1)}%</b>
                  </div>
                </div>
                <span className={`diag__tier ${tier.cls}`}><i /> {tier.label}</span>
                {result.specialist_consultation_recommended ? (
                  <p className="diag__consult is-on">
                    <Icon name="doctor" size={15} />
                    Confidence is below the consultation threshold — the model recommends referring this case to a specialist for review.
                  </p>
                ) : (
                  <p className="diag__consult">
                    <Icon name="check" size={15} />
                    Confidence is above the consultation threshold. Model {result.model_version} scored {result.evaluated_accuracy}% on the digital-twin evaluation.
                  </p>
                )}
                <p className="diag__disclaimer">
                  Decision-support output, not a medical diagnosis. Always confirm with a qualified clinician.
                </p>
              </div>
            )}
          </motion.section>
        </div>
      )}
    </ConsoleShell>
  );
}
