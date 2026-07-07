import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Reveal, stagger, staggerItem } from "../lib/motion";
import { useAuth } from "../lib/auth";
import "./Sections.css";

export function Intro() {
  return (
    <section className="section intro" id="about">
      <div className="container intro__grid">
        <Reveal>
          <span className="eyebrow"><span className="dot" /> Privacy-first by design</span>
        </Reveal>
        <Reveal delay={0.08}>
          <p className="intro__text">
            MedChain is a platform for <em>collaborative medical AI</em>. Hospitals train on
            their own data and share only model updates — never patient records. Every
            contribution is validated, aggregated, and written to a tamper-evident audit trail.
          </p>
        </Reveal>
      </div>
    </section>
  );
}

const trustSignals = [
  "Privacy-first",
  "Federated by design",
  "On-chain audit trail",
  "Role-based access",
  "Encrypted in transit",
  "No raw data egress",
];

export function TechMarquee() {
  return (
    <div className="techrow" aria-label="Platform principles">
      <div className="techrow__track">
        {[0, 1].map((group) => (
          <div className="techrow__group" key={group}>
            {trustSignals.map((item) => <span key={item}>{item}</span>)}
          </div>
        ))}
      </div>
    </div>
  );
}

const benefits = [
  {
    no: "01",
    title: "Patient data stays put",
    body: "Hospitals train locally and share only encrypted model updates. Raw records never leave your institution's network.",
    foot: "Privacy by architecture, not by policy.",
  },
  {
    no: "02",
    title: "Every contribution is verifiable",
    body: "Each validated update is fingerprinted and written to an immutable on-chain ledger, giving partners and regulators a tamper-evident audit trail.",
    foot: "Provenance you can prove.",
  },
  {
    no: "03",
    title: "Stronger models, together",
    body: "Sample-weighted federated averaging combines insight from every participating hospital into one continually improving shared model.",
    foot: "Greater than any single dataset.",
  },
];

export function Benefits() {
  return (
    <section className="section" id="features">
      <div className="container">
        <div className="sec-center">
          <Reveal><span className="eyebrow"><span className="dot" /> Implemented service</span></Reveal>
          <Reveal delay={0.06}><h2 className="section-title">Built for trust at every step</h2></Reveal>
        </div>
        <motion.div className="grid benefits" variants={stagger} initial="hidden" whileInView="show" viewport={{ once: true, margin: "-70px" }}>
          {benefits.map((benefit) => (
            <motion.div key={benefit.no} variants={staggerItem} className="card benefit">
              <span className="benefit__no">{benefit.no}</span>
              <h3>{benefit.title}</h3>
              <p>{benefit.body}</p>
              <span className="benefit__foot"><span className="dot" /> {benefit.foot}</span>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}

function MiniNetwork() {
  return (
    <svg viewBox="0 0 300 200" className="mini" aria-label="Hospital clients sending updates to the backend">
      <circle cx="150" cy="100" r="35" fill="#f399b3" opacity="0.9" />
      {[[55, 45], [245, 45], [245, 155], [55, 155]].map(([x, y], index) => (
        <g key={`${x}-${y}`}>
          <line x1={x} y1={y} x2="150" y2="100" stroke="#3a3a3a" />
          <motion.circle
            r="3"
            fill="#f399b3"
            animate={{ cx: [x, 150], cy: [y, 100], opacity: [0, 1, 0] }}
            transition={{ duration: 2, delay: index * 0.4, repeat: Infinity }}
          />
          <circle cx={x} cy={y} r="11" fill="#0d0d0d" stroke="#3a3a3a" />
        </g>
      ))}
      <text x="150" y="104" textAnchor="middle" fontSize="10" fill="#0a0a0a">API</text>
    </svg>
  );
}

function MiniStore() {
  return (
    <svg viewBox="0 0 300 200" className="mini" aria-label="Persistent backend records">
      {[0, 1, 2].map((index) => (
        <motion.g key={index} initial={{ opacity: 0.3 }} whileInView={{ opacity: 1 }} transition={{ delay: index * 0.2 }}>
          <rect x={42 + index * 76} y={70 + index * 8} width="64" height="58" rx="10" fill="#121212" stroke="#3a3a3a" />
          <text x={74 + index * 76} y={98 + index * 8} textAnchor="middle" fontSize="9" fill="#f399b3">record</text>
          <text x={74 + index * 76} y={113 + index * 8} textAnchor="middle" fontSize="8" fill="#6f6f6f">persisted</text>
        </motion.g>
      ))}
    </svg>
  );
}

function MiniBars() {
  return (
    <svg viewBox="0 0 300 200" className="mini" aria-label="Sample-weighted aggregation">
      {[52, 84, 66, 100, 78].map((height, index) => (
        <motion.rect
          key={height}
          x={44 + index * 46}
          width="26"
          rx="6"
          fill={index === 3 ? "#f399b3" : "#2a2a2a"}
          initial={{ height: 0, y: 160 }}
          whileInView={{ height, y: 160 - height }}
          transition={{ duration: 0.7, delay: index * 0.08 }}
          viewport={{ once: true }}
        />
      ))}
      <line x1="30" y1="160" x2="270" y2="160" stroke="#333" />
    </svg>
  );
}

const highlights = [
  {
    tag: "For hospitals",
    title: "Contribute without exposing data",
    body: "Participating hospitals submit trained weights and local metrics through a secure API. Your patient data is never transmitted, stored centrally, or reconstructed.",
    visual: <MiniNetwork />,
  },
  {
    tag: "For administrators",
    title: "Full control and oversight",
    body: "Role-based access governs who can launch rounds, verify submissions, and manage the consortium — and every action is authenticated and logged.",
    visual: <MiniStore />,
  },
  {
    tag: "For researchers",
    title: "Results you can trust",
    body: "Approved model versions and audit metadata are available for review, backed by a verifiable on-chain record of exactly how each version was produced.",
    visual: <MiniBars />,
  },
];

export function Highlights() {
  return (
    <section className="section" id="solution">
      <div className="container">
        <div className="hl-stack">
          {highlights.map((highlight, index) => (
            <Reveal key={highlight.tag}>
              <div className={`hl ${index % 2 ? "hl--flip" : ""}`}>
                <div className="hl__copy">
                  <span className="eyebrow"><span className="dot" /> {highlight.tag}</span>
                  <h3>{highlight.title}</h3>
                  <p>{highlight.body}</p>
                </div>
                <div className="hl__visual card">{highlight.visual}</div>
              </div>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  );
}

export function FinalCTA() {
  const { isAuthenticated } = useAuth();
  return (
    <section className="section cta">
      <div className="cta__glow" aria-hidden />
      <div className="container sec-center cta__inner">
        <Reveal><h2 className="cta__title">Bring your institution into the network</h2></Reveal>
        <Reveal delay={0.08}>
          <p className="cta__lead">Improve medical AI together — with privacy, provenance, and control built in.</p>
        </Reveal>
        <Reveal delay={0.14}>
          <Link to={isAuthenticated ? "/dashboard" : "/request-access"} className="btn btn-primary">
            {isAuthenticated ? "Open the Console" : "Request access"}
          </Link>
        </Reveal>
      </div>
    </section>
  );
}
