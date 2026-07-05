import { Link } from "react-router-dom";
import "./Footer.css";

const refs = [
  "FedAvg — McMahan et al., AISTATS 2017",
  "Federated Optimization — Konečný et al., 2016",
  "Secure Aggregation — ACM CCS 2017",
];

export default function Footer() {
  return (
    <footer className="footer">
      <div className="container footer__inner">
        <div className="footer__brand">
          <span className="footer__logo">
            MedChain <em>AI</em>
          </span>
          <p>
            A persistent backend coordinator for authenticated federated model updates.
          </p>
          <span className="footer__pill"><span className="dot" /> Team MedChain AI</span>
        </div>

        <div className="footer__cols">
          <div>
            <h5>Explore</h5>
            <a href="/#about">About</a>
            <a href="/#features">Benefits</a>
            <a href="/#solution">How it works</a>
            <Link to="/dashboard">Live Dashboard</Link>
          </div>
          <div className="footer__refs">
            <h5>Research</h5>
            {refs.map((r) => <span key={r}>{r}</span>)}
          </div>
        </div>
      </div>

      <div className="container footer__bottom">
        <span>© {new Date().getFullYear()} MedChain AI</span>
        <span>Backend-backed service</span>
      </div>
    </footer>
  );
}
