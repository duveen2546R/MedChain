import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import AuthScene, { authStagger, authItem } from "../components/AuthScene";
import Icon from "../components/Icon";
import { roleLabel, useAuth } from "../lib/auth";
import { ApiError, apiJson } from "../lib/api";
import "./Auth.css";

const STEPS = [
  {
    icon: "hospital",
    title: "You've been invited",
    desc: "A MedChain administrator created an invitation for your organization and role — no self-signup needed.",
  },
  {
    icon: "lock",
    title: "Set your password",
    desc: "Choose a password to activate your account. Your email and role are already set by the invitation.",
  },
  {
    icon: "spark",
    title: "Start contributing",
    desc: "Once activated you can sign in and begin working inside your organization's console.",
  },
];

export default function Register() {
  const { acceptInvite } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const inviteToken = params.get("token") || "";

  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [loadingPreview, setLoadingPreview] = useState(Boolean(inviteToken));
  const [form, setForm] = useState({ name: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  useEffect(() => {
    if (!inviteToken) {
      setLoadingPreview(false);
      setPreviewError("This page needs an invitation link. Ask an administrator to invite you.");
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await apiJson(`/auth/invitations/token/${inviteToken}`);
        if (!cancelled) setPreview(data);
      } catch (err) {
        if (!cancelled) {
          setPreviewError(
            err instanceof ApiError && err.status === 410
              ? "This invitation has expired or already been used."
              : "This invitation link is invalid."
          );
        }
      } finally {
        if (!cancelled) setLoadingPreview(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [inviteToken]);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await acceptInvite(inviteToken, form.name, form.password);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth auth--split">
      <AuthScene />

      <div className="auth__grid">
        <motion.div className="auth__intro auth__intro--side" variants={authStagger} initial="hidden" animate="show">
          <motion.div variants={authItem}>
            <Link to="/" className="auth__brand">
              MedChain <em>AI</em>
            </Link>
          </motion.div>
          <motion.h1 className="auth__heading" variants={authItem}>
            Accept your <em>invitation</em>
          </motion.h1>
          <motion.p className="auth__lead" variants={authItem}>
            Activate the account an administrator created for you and join your organization on MedChain.
          </motion.p>

          <motion.ol className="auth__steps" variants={authItem}>
            {STEPS.map((step, index) => (
              <li key={step.title} className="auth__step">
                <span className="auth__step-num tnum">{index + 1}</span>
                <span className="auth__feature-copy">
                  <b><Icon name={step.icon} size={13} /> {step.title}</b>
                  <span>{step.desc}</span>
                </span>
              </li>
            ))}
          </motion.ol>
        </motion.div>

        <div className="auth__side">
          <motion.div
            className="auth__shell"
            initial={{ opacity: 0, y: 30, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.9, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="auth__halo" aria-hidden />
            <div className="auth__card">
              {loadingPreview ? (
                <p className="auth__lead">Checking your invitation…</p>
              ) : previewError ? (
                <div className="auth__form">
                  <div className="auth__error">{previewError}</div>
                  <Link to="/request-access" className="btn btn-primary auth__submit">
                    Request access instead
                  </Link>
                </div>
              ) : (
                <form className="auth__form" onSubmit={onSubmit}>
                  <div className="auth__invite-meta">
                    <p>
                      Joining <b>{preview.org_name}</b> as <b>{roleLabel(preview.role)}</b>
                    </p>
                    <p className="auth__aside">{preview.email}</p>
                  </div>

                  <label className="auth__field">
                    <span>Full name</span>
                    <input value={form.name} onChange={set("name")} placeholder="Dr. Naomi Chen" required />
                  </label>
                  <label className="auth__field">
                    <span>Password</span>
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={form.password}
                      onChange={set("password")}
                      placeholder="At least 8 characters"
                      minLength={8}
                      required
                    />
                  </label>

                  {error && <div className="auth__error">{error}</div>}

                  <button type="submit" className="btn btn-primary auth__submit" disabled={busy}>
                    {busy ? "Activating…" : "Activate account"}
                  </button>
                </form>
              )}
            </div>
          </motion.div>

          <motion.p
            className="auth__switch"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.55 }}
          >
            Already have an account? <Link to="/login">Sign in</Link>
          </motion.p>
        </div>
      </div>
    </main>
  );
}
