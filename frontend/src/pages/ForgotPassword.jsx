import { useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import AuthScene, { authStagger, authItem } from "../components/AuthScene";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import "./Auth.css";

export default function ForgotPassword() {
  const { forgotPassword } = useAuth();
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await forgotPassword(email);
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
            Reset your <em>password</em>
          </motion.h1>
          <motion.p className="auth__lead" variants={authItem}>
            Enter your account email and we'll send a link to set a new password.
          </motion.p>
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
              {done ? (
                <div className="auth__form">
                  <div className="auth__invite-meta">
                    <p><b>Check your inbox.</b></p>
                    <p className="auth__aside">
                      If an account exists for that email, we've sent a link to reset your password.
                    </p>
                  </div>
                  <Link to="/login" className="btn btn-primary auth__submit">Back to sign in</Link>
                </div>
              ) : (
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

                  {error && <div className="auth__error">{error}</div>}

                  <button type="submit" className="btn btn-primary auth__submit" disabled={busy}>
                    {busy ? "Sending…" : "Send reset link"}
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
            Remembered it? <Link to="/login">Sign in</Link>
          </motion.p>
        </div>
      </div>
    </main>
  );
}
