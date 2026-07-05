import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from "../lib/auth";
import "./Hero.css";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: (i) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.8, delay: 0.1 + i * 0.12, ease: [0.22, 1, 0.36, 1] },
  }),
};

export default function Hero() {
  const { isAuthenticated } = useAuth();
  return (
    <section className="hero">
      <div className="container hero__copy">
        <motion.h1 className="hero__title" custom={0} variants={fadeUp} initial="hidden" animate="show">
          Coordinate Real Federated
          <br />
          Model Updates
        </motion.h1>

        <motion.p className="hero__lead" custom={1} variants={fadeUp} initial="hidden" animate="show">
          An authenticated backend service designed for{" "}
          <br className="hero__br" />
          hospital clients, administrators, and researchers.
        </motion.p>

        <motion.div className="hero__actions" custom={2} variants={fadeUp} initial="hidden" animate="show">
          {isAuthenticated ? (
            <Link to="/dashboard" className="btn btn-primary">Open the Console</Link>
          ) : (
            <>
              <Link to="/register" className="btn btn-primary">Get Started</Link>
              <Link to="/login" className="btn btn-ghost">Sign in</Link>
            </>
          )}
        </motion.div>
      </div>

      {/* rose stage glow */}
      <div className="stage" aria-hidden>
        <div className="stage__glow stage__glow--a" />
        <div className="stage__occ stage__occ--a" />
        <div className="stage__glow stage__glow--b" />
        <div className="stage__wing stage__wing--l" />
        <div className="stage__wing stage__wing--r" />
        <div className="stage__floor" />
        <div className="stage__fade" />
      </div>
    </section>
  );
}
