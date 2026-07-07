import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import AuthScene, { authStagger, authItem } from "../components/AuthScene";
import Icon from "../components/Icon";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import "./Auth.css";

const orgTypes = [
  { id: "hospital", title: "Hospital / Consortium", desc: "Train, verify, and shape the global model." },
  { id: "research", title: "Research Partner", desc: "Read approved model and audit metadata." },
];

export default function RequestAccess() {
  const { requestAccess } = useAuth();

  const [form, setForm] = useState({
    organization_name: "",
    organization_type: "hospital",
    contact_name: "",
    email: "",
    message: "",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await requestAccess(form);
      setDone(true);
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
            Request <em>access</em>
          </motion.h1>
          <motion.p className="auth__lead" variants={authItem}>
            MedChain is invite-only. Tell us about your organization and a platform administrator
            will review your request and send an invitation.
          </motion.p>
          <motion.p className="auth__aside" variants={authItem}>
            <Icon name="lock" size={13} /> Clinics that only query the model are onboarded directly by an
            administrator — reach out and we'll set you up.
          </motion.p>
        </motion.div>

        <div className="auth__side">
          <motion.div
            className="auth__shell auth__shell--wide"
            initial={{ opacity: 0, y: 30, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 0.9, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="auth__halo" aria-hidden />
            <div className="auth__card">
              {done ? (
                <div className="auth__form">
                  <div className="auth__invite-meta">
                    <p><b>Request received.</b></p>
                    <p className="auth__aside">
                      A platform administrator will review your request. If approved, you'll receive an
                      invitation link by email to activate your account.
                    </p>
                  </div>
                  <Link to="/login" className="btn btn-primary auth__submit">Back to sign in</Link>
                </div>
              ) : (
                <form className="auth__form" onSubmit={onSubmit}>
                  <div className="auth__types" role="radiogroup" aria-label="Organization type">
                    {orgTypes.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        role="radio"
                        aria-checked={form.organization_type === t.id}
                        className={`auth__type ${form.organization_type === t.id ? "is-active" : ""}`}
                        onClick={() => setForm((f) => ({ ...f, organization_type: t.id }))}
                      >
                        <span className="auth__type-radio" aria-hidden />
                        <span className="auth__type-copy">
                          <b>{t.title}</b>
                          <span>{t.desc}</span>
                        </span>
                      </button>
                    ))}
                  </div>

                  <div className="auth__row">
                    <label className="auth__field">
                      <span>Contact name</span>
                      <input value={form.contact_name} onChange={set("contact_name")} placeholder="Dr. Naomi Chen" required />
                    </label>
                    <label className="auth__field">
                      <span>Organization</span>
                      <input value={form.organization_name} onChange={set("organization_name")} placeholder="Riverside Institute" required />
                    </label>
                  </div>

                  <label className="auth__field">
                    <span>Work email</span>
                    <input type="email" autoComplete="email" value={form.email} onChange={set("email")} placeholder="you@hospital.org" required />
                  </label>
                  <label className="auth__field">
                    <span>Anything we should know? (optional)</span>
                    <input value={form.message} onChange={set("message")} placeholder="Tell us about your use case" />
                  </label>

                  {error && <div className="auth__error">{error}</div>}

                  <button type="submit" className="btn btn-primary auth__submit" disabled={busy}>
                    {busy ? "Submitting…" : "Request access"}
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
