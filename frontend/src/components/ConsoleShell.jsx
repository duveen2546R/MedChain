import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import Icon from "./Icon";
import ConsoleTabs from "./ConsoleTabs";
import { roleLabel, useAuth } from "../lib/auth";
import "../pages/Dashboard.css";

/* Shared frame for the secondary console pages (Diagnosis, Explorer, Audit):
   same ambient scene and glass header as the Dashboard, lighter chrome. */
export default function ConsoleShell({ here, title, titleEm, caption, children }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  function onLogout() {
    logout();
    navigate("/");
  }

  return (
    <main className="dash">
      <div className="dash__scene" aria-hidden>
        <div className="dash__scene-glow dash__scene-glow--top" />
        <div className="dash__orb dash__orb--a" />
        <div className="dash__orb dash__orb--b" />
        <div className="dash__noise" />
      </div>

      <div className="container dash__inner">
        <motion.header
          className="dash__nav"
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          <nav className="dash__crumb" aria-label="Breadcrumb">
            <Link to="/" className="dash__crumb-brand">
              MedChain <em>AI</em>
            </Link>
            <span className="dash__crumb-sep">/</span>
            <span className="dash__crumb-here">{here}</span>
          </nav>

          <ConsoleTabs />

          <div className="dash__nav-right">
            {user && (
              <div className="dash__user">
                <span className="dash__user-avatar">{(user.name || user.email || "?").charAt(0).toUpperCase()}</span>
                <span className="dash__user-meta">
                  <b>{user.name || user.email}</b>
                  <span>{roleLabel(user.role)}</span>
                </span>
                <button className="dash__iconbtn" onClick={onLogout} title="Sign out" aria-label="Sign out">
                  <Icon name="logout" size={16} />
                </button>
              </div>
            )}
          </div>
        </motion.header>

        <motion.section
          className="dash__hero"
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="dash__hero-copy">
            <h1 className="dash__title">
              {title} {titleEm && <em>{titleEm}</em>}
            </h1>
            <p className="dash__phase">{caption}</p>
          </div>
        </motion.section>

        {children}
      </div>
    </main>
  );
}
