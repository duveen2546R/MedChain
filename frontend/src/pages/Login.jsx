import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import AuthScene, { authStagger, authItem } from "../components/AuthScene";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import "./Auth.css";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = location.state?.from || "/dashboard";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(email, password);
      navigate(from, { replace: true });
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
          Welcome <em>back</em>
        </motion.h1>
        <motion.p className="auth__lead" variants={authItem}>
          Sign in to launch training rounds, verify submissions, and monitor the shared model.
        </motion.p>
      </motion.div>

      <motion.div
        className="auth__shell"
        initial={{ opacity: 0, y: 30, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.9, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="auth__halo" aria-hidden />
        <div className="auth__card">
          <form className="auth__form" onSubmit={onSubmit}>
            <label className="auth__field">
              <span>Email</span>
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@hospital.org"
                required
              />
            </label>
            <label className="auth__field">
              <span>Password</span>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />
            </label>

            {error && <div className="auth__error">{error}</div>}

            <button type="submit" className="btn btn-primary auth__submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
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
        New to MedChain? <Link to="/register">Create an account</Link>
      </motion.p>
    </main>
  );
}
