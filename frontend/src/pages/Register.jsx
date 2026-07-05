import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
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
      <div className="auth__glow" aria-hidden />
      <motion.div
        className="auth__card auth__card--wide"
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
      >
        <Link to="/" className="auth__brand">
          MedChain <em>AI</em>
        </Link>
        <h1 className="auth__title">Join the network</h1>
        <p className="auth__sub">Create an account to use the federated update service.</p>

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
                <b>{t.title}</b>
                <span>{t.desc}</span>
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

        <p className="auth__switch">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </motion.div>
    </main>
  );
}
