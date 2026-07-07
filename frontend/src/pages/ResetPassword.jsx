import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import AuthScene, { authStagger, authItem } from "../components/AuthScene";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import "./Auth.css";

export default function ResetPassword() {
  const { resetPassword } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const resetToken = params.get("token") || "";

  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError("");
    if (!resetToken) {
      setError("This reset link is missing its token. Request a new one.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setBusy(true);
    try {
      await resetPassword(resetToken, password);
      setDone(true);
      setTimeout(() => navigate("/login", { replace: true }), 1800);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 400
          ? "This reset link is invalid or has expired. Request a new one."
          : err instanceof ApiError
            ? err.message
            : "Something went wrong. Try again."
      );
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
            Choose a new <em>password</em>
          </motion.h1>
          <motion.p className="auth__lead" variants={authItem}>
            Set a new password for your MedChain account.
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
                    <p><b>Password updated.</b></p>
                    <p className="auth__aside">Redirecting you to sign in…</p>
                  </div>
                  <Link to="/login" className="btn btn-primary auth__submit">Sign in now</Link>
                </div>
              ) : (
                <form className="auth__form" onSubmit={onSubmit}>
                  <label className="auth__field">
                    <span>New password</span>
                    <input
                      type="password"
                      autoComplete="new-password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="At least 8 characters"
                      minLength={8}
                      required
                    />
                  </label>

                  {error && <div className="auth__error">{error}</div>}

                  <button type="submit" className="btn btn-primary auth__submit" disabled={busy}>
                    {busy ? "Updating…" : "Update password"}
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
            Need a new link? <Link to="/forgot-password">Request one</Link>
          </motion.p>
        </div>
      </div>
    </main>
  );
}
