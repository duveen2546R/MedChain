import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import Icon from "../components/Icon";
import { useFederatedBackend } from "../lib/useFederatedBackend";
import { canRunRounds, roleLabel, useAuth } from "../lib/auth";
import "./Dashboard.css";

const statusMeta = {
  idle: { label: "Idle", cls: "s-idle" },
  training: { label: "Training", cls: "s-training" },
  submitted: { label: "Submitting", cls: "s-submitted" },
  validated: { label: "Verified", cls: "s-validated" },
  rejected: { label: "Rejected", cls: "s-rejected" },
};

export default function Dashboard() {
  const service = useFederatedBackend();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const role = user?.role;
  const mayRun = canRunRounds(role);
  const latest = service.versions[service.versions.length - 1];
  const first = service.versions[0];

  function onLogout() {
    logout();
    navigate("/");
  }

  // chart geometry
  const chartW = 620;
  const chartH = 180;
  const accMin = 0;
  const accMax = 100;
  const points = service.versions.map((v, i) => {
    const x = service.versions.length === 1 ? 0 : (i / (service.versions.length - 1)) * chartW;
    const y = chartH - ((v.accuracy - accMin) / (accMax - accMin)) * chartH;
    return { x, y, v };
  });
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaPath =
    points.length > 1
      ? `${linePath} L ${chartW} ${chartH} L 0 ${chartH} Z`
      : "";

  return (
    <main className="dash">
      <div className="dash__bg" />
      <div className="container dash__inner">
        {/* header */}
        <header className="dash__head">
          <div>
            <span className="eyebrow"><span className="dot" /> {service.backendConnected ? "FastAPI backend · connected" : "Backend unavailable"}</span>
            <h1 className="dash__title">Federated Training Console</h1>
            <p className="dash__phase">
              <span className={`dash__pulse ${service.running ? "is-on" : ""}`} />
              {service.phase}
            </p>
          </div>
          <div className="dash__account">
            {user && (
              <div className="dash__user">
                <span className="dash__user-avatar">{(user.name || user.email || "?").charAt(0).toUpperCase()}</span>
                <span className="dash__user-meta">
                  <b>{user.name || user.email}</b>
                  <span>{roleLabel(role)}</span>
                </span>
                <button className="dash__logout" onClick={onLogout} title="Sign out">Sign out</button>
              </div>
            )}
            <div className="dash__controls">
              <button
                className="btn btn-primary"
                onClick={service.runRound}
                disabled={service.running || !mayRun || !service.backendConnected}
                title={mayRun ? "Start a training round" : "Requires a Hospital Admin or Platform Admin role"}
              >
                {service.running ? "Round active" : "Start Round"}
                {!service.running && <Icon name="arrow" size={16} />}
              </button>
            </div>
            {!mayRun && (
              <span className="dash__rolehint">Signed in as {roleLabel(role)} — this role has read-only access to the console.</span>
            )}
          </div>
        </header>

        {/* KPI row */}
        <section className="kpi-row">
          <div className="card kpi">
            <span className="kpi__label">Reported accuracy</span>
            <b className="kpi__value gradient-text">{latest ? `${latest.accuracy}%` : "—"}</b>
            <span className="kpi__sub">
              {latest && first
                ? `${(latest.accuracy - first.accuracy).toFixed(2)}% across aggregated versions`
                : "No model has been aggregated"}
            </span>
          </div>
          <div className="card kpi">
            <span className="kpi__label">Model version</span>
            <b className="kpi__value">{latest?.version || "—"}</b>
            <span className="kpi__sub">Round {service.round}</span>
          </div>
          <div className="card kpi">
            <span className="kpi__label">Round submissions</span>
            <b className="kpi__value">{service.submissionsReceived}/{service.submissionsRequired}</b>
            <span className="kpi__sub">hospital updates received by API</span>
          </div>
          <div className="card kpi">
            <span className="kpi__label">Backend</span>
            <b className="kpi__value">{service.backendConnected ? "Online" : "Offline"}</b>
            <span className="kpi__sub">MongoDB-backed service</span>
          </div>
        </section>

        <div className="dash__grid">
          {/* Hospitals */}
          <section className="card panel panel--nodes">
            <div className="panel__head">
              <h3>Hospital Nodes</h3>
              <span className="panel__tag">{service.hospitals.length} in consortium</span>
            </div>
            <div className="nodes">
              {service.hospitals.map((h) => {
                const m = statusMeta[h.status] || statusMeta.idle;
                return (
                  <motion.div
                    key={h.id}
                    className={`node ${service.activeNode === h.id ? "node--active" : ""}`}
                    layout
                    animate={h.status === "training" ? { scale: [1, 1.01, 1] } : { scale: 1 }}
                    transition={{ duration: 1, repeat: h.status === "training" ? Infinity : 0 }}
                  >
                    <div className="node__top">
                      <div className="node__id">{h.id.toUpperCase()}</div>
                      <div className="node__meta">
                        <b>{h.name}</b>
                        <span>{h.specialty} · {h.region} · {h.samples.toLocaleString()} samples</span>
                      </div>
                      <span className={`node__status ${m.cls}`}>{m.label}</span>
                    </div>
                    <div className="node__bars">
                      <div className="node__rep">
                        <span>Reputation</span>
                        <div className="bar"><motion.i animate={{ width: `${h.reputation}%` }} /></div>
                        <b>{h.reputation}</b>
                      </div>
                      {h.contribution > 0 && (
                        <span className="node__contrib">weight {h.contribution}%</span>
                      )}
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </section>

          {/* Backend round status */}
          <section className="card panel panel--status">
            <div className="panel__head">
              <h3>Backend Round Status</h3>
              <span className="panel__tag">persistent API state</span>
            </div>
            <div className="round-status">
              <div className="round-status__content">
                <Icon name="shield" size={22} />
                <p>{service.phase}</p>
                <p>
                  The backend has received {service.submissionsReceived} of {service.submissionsRequired} required updates.
                </p>
              </div>
            </div>
          </section>

          {/* Accuracy chart */}
          <section className="card panel panel--chart">
            <div className="panel__head">
              <h3>Reported Accuracy History</h3>
              <span className="panel__tag">sample-weighted client metrics</span>
            </div>
            <svg className="chart" viewBox={`0 0 ${chartW} ${chartH + 28}`} preserveAspectRatio="none">
              <defs>
                <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="rgba(243,153,179,0.32)" />
                  <stop offset="100%" stopColor="rgba(243,153,179,0.02)" />
                </linearGradient>
                <linearGradient id="stroke" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#ffd9e1" />
                  <stop offset="100%" stopColor="#f399b3" />
                </linearGradient>
              </defs>
              {[0, 0.5, 1].map((g) => (
                <line key={g} x1="0" x2={chartW} y1={chartH * g} y2={chartH * g} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
              ))}
              {areaPath && <motion.path d={areaPath} fill="url(#fill)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} />}
              <motion.path
                d={linePath}
                fill="none"
                stroke="url(#stroke)"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                key={linePath}
                initial={{ pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ duration: 0.6 }}
              />
              {points.map((p) => (
                <g key={p.v.version}>
                  <circle cx={p.x} cy={p.y} r="4" fill="#000000" stroke="url(#stroke)" strokeWidth="2" />
                  <text x={p.x} y={chartH + 20} textAnchor="middle" fontSize="11" fill="var(--text-faint)">{p.v.version}</text>
                </g>
              ))}
            </svg>
            <div className="chart__scale">
              <span>{accMax}%</span><span>{accMin}%</span>
            </div>
          </section>

          {/* Version history */}
          <section className="card panel panel--versions">
            <div className="panel__head">
              <h3>Version History</h3>
              <span className="panel__tag">{service.versions.length} releases</span>
            </div>
            <div className="versions">
              {[...service.versions].reverse().map((v) => (
                <div className="ver" key={v.version}>
                  <span className="ver__tag">{v.version}</span>
                  <div className="ver__mid">
                    <b>{v.accuracy}%</b>
                    <span>Round {v.round} · {v.contributors} contributor{v.contributors === 1 ? "" : "s"}</span>
                  </div>
                  <div className="ver__bar"><i style={{ width: `${v.accuracy}%` }} /></div>
                </div>
              ))}
            </div>
          </section>
        </div>

        <p className="dash__foot">
          Every value on this dashboard comes from the authenticated FastAPI service. Hospital clients
          submit model updates through the API; the backend validates their schema, persists them, and
          performs sample-weighted aggregation. There is no offline simulation.
        </p>
      </div>
    </main>
  );
}
