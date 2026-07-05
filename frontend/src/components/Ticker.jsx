import "./Ticker.css";

const phrase = "Privacy-first federated learning for healthcare";

export default function Ticker() {
  return (
    <div className="ticker" aria-hidden>
      <div className="ticker__track">
        {[0, 1].map((k) => (
          <div className="ticker__group" key={k}>
            {Array.from({ length: 6 }).map((_, i) => (
              <span key={i}>{phrase}</span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
