import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import AuthScene, { authStagger, authItem } from "../components/AuthScene";
import Icon from "../components/Icon";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";
import "./Auth.css";

const FEATURES = [
  {
    icon: "route",
    title: "Federated training rounds",
    desc: "Hospitals train on their own data; only weight vectors and measured metrics reach the network.",
  },
  {
    icon: "shield",
    title: "Digital-twin validation gate",
    desc: "Every update is stress-tested on synthetic cases before it can touch the global model.",
  },
  {
    icon: "chain",
    title: "Consortium blockchain",
    desc: "Contributions and reputation live in hash-linked, ECDSA-signed blocks, re-verified on every start.",
  },
  {
    icon: "brain",
    title: "Confidence-based diagnosis",
    desc: "Clinics query the aggregated model and get confidence tiers with specialist-referral flags.",
  },
];

const STATS = [
  { value: "30", label: "diagnostic features" },
  { value: "4", label: "gate checks per update" },
  { value: "7777", label: "consortium chain" },
  { value: "0", label: "patient rows shared" },
];

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
            Welcome <em>back</em>
          </motion.h1>
          <motion.p className="auth__lead" variants={authItem}>
            Sign in to launch training rounds, verify submissions, audit the chain, and query the shared model.
          </motion.p>

          <motion.ul className="auth__features" variants={authItem}>
            {FEATURES.map((feature) => (
              <li key={feature.title} className="auth__feature">
                <span className="auth__feature-icon">
                  <Icon name={feature.icon} size={16} />
                </span>
                <span className="auth__feature-copy">
                  <b>{feature.title}</b>
                  <span>{feature.desc}</span>
                </span>
              </li>
            ))}
          </motion.ul>

          <motion.div className="auth__stats" variants={authItem}>
            {STATS.map((stat) => (
              <span key={stat.label} className="auth__stat">
                <b className="tnum">{stat.value}</b>
                <span>{stat.label}</span>
              </span>
            ))}
          </motion.div>
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
                <Link to="/forgot-password" className="auth__link">Forgot password?</Link>
              </form>
            </div>
          </motion.div>

          <motion.p
            className="auth__switch"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.55 }}
          >
            Need access? <Link to="/request-access">Request an invitation</Link>
          </motion.p>
        </div>
      </div>
    </main>
  );
}
