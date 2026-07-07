import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../lib/auth";
import "./DockNav.css";

function HomeIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1Z" />
    </svg>
  );
}
function GridIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
      <rect x="4" y="4" width="7" height="7" rx="1.6" />
      <rect x="13" y="4" width="7" height="7" rx="1.6" />
      <rect x="4" y="13" width="7" height="7" rx="1.6" />
      <rect x="13" y="13" width="7" height="7" rx="1.6" />
    </svg>
  );
}
function ChartIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
      <path d="M4 20V10m6 10V4m6 16v-7" />
      <path d="M3 20h18" />
    </svg>
  );
}
function BellIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6" />
      <path d="M10 20a2.2 2.2 0 0 0 4 0" />
    </svg>
  );
}

export default function DockNav() {
  const { pathname } = useLocation();
  const { isAuthenticated } = useAuth();
  const onDashboard = pathname === "/dashboard";

  let cta;
  if (onDashboard) cta = { to: "/", label: "Back to site" };
  else if (isAuthenticated) cta = { to: "/dashboard", label: "Open Console" };
  else cta = { to: "/request-access", label: "Get Started" };

  return (
    <motion.nav
      className="dock"
      initial={{ y: 90, x: "-50%", opacity: 0 }}
      animate={{ y: 0, x: "-50%", opacity: 1 }}
      transition={{ duration: 0.7, delay: 0.5, ease: [0.22, 1, 0.36, 1] }}
      aria-label="Primary"
    >
      <Link to="/" className={`dock__icon ${!onDashboard ? "is-active" : ""}`} aria-label="Home">
        <HomeIcon />
      </Link>
      <a href="/#features" className="dock__icon" aria-label="Features">
        <GridIcon />
      </a>
      <Link to="/dashboard" className={`dock__icon ${onDashboard ? "is-active" : ""}`} aria-label="Dashboard">
        <ChartIcon />
      </Link>
      <Link to={cta.to} className="dock__cta">
        <BellIcon />
        {cta.label}
      </Link>
    </motion.nav>
  );
}
