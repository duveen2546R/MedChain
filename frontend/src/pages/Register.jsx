import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import AuthScene, { authStagger, authItem } from "../components/AuthScene";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import "./Auth.css";

const accountTypes = [
  { id: "hospital", title: "Hospital / Consortium", desc: "Train, verify, and shape the global model." },
  { id: "clinic", title: "Clinic", desc: "Query the global model via API." },
  { id: "research", title: "Research Partner", desc: "Read approved model and audit metadata." },
];

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    name: "",
    email: "",
    organization: "",
    password: "",
    account_type: "hospital",
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await register(form);
      navigate("/dashboard", { replace: true });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth">
      <AuthScene />

      <motion.div className="auth__intro" variants={authStagger} initial="hidden" animate="show">
        <motion.div variants={authItem}>
          <Link to="/" className="auth__brand">
            MedChain <em>AI</em>
          </Link>
        </motion.div>
        <motion.h1 className="auth__heading" variants={authItem}>
          Join the <em>network</em>
        </motion.h1>
        <motion.p className="auth__lead" variants={authItem}>
          Put your data to work without giving it up — contribute to, and benefit from, the shared model.
        </motion.p>
      </motion.div>

      <motion.div
        className="auth__shell auth__shell--wide"
        initial={{ opacity: 0, y: 30, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.9, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="auth__halo" aria-hidden />
        <div className="auth__card">
          <form className="auth__form" onSubmit={onSubmit}>
            <div className="auth__types" role="radiogroup" aria-label="Account type">
              {accountTypes.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="radio"
                  aria-checked={form.account_type === t.id}
                  className={`auth__type ${form.account_type === t.id ? "is-active" : ""}`}
                  onClick={() => setForm((f) => ({ ...f, account_type: t.id }))}
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
                <span>Full name</span>
                <input value={form.name} onChange={set("name")} placeholder="Dr. Naomi Chen" required />
              </label>
              <label className="auth__field">
                <span>Organization</span>
                <input value={form.organization} onChange={set("organization")} placeholder="Riverside Institute" required />
              </label>
            </div>

            <label className="auth__field">
              <span>Email</span>
              <input type="email" autoComplete="email" value={form.email} onChange={set("email")} placeholder="you@hospital.org" required />
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
              {busy ? "Creating account…" : "Create account"}
            </button>
          </form>
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
    </main>
  );
}
