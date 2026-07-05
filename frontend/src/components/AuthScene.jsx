// Shared ambient backdrop for the auth pages — rose stage lighting and
// slowly rising particles, echoing the landing hero. Purely decorative.

// Deterministic pseudo-random particle field (stable across re-renders).
const particles = Array.from({ length: 18 }, (_, i) => {
  const seed = (i * 2654435761) % 97;
  return {
    left: `${(i * 53 + 11) % 100}%`,
    size: 2 + (i % 3),
    duration: 14 + (seed % 12),
    delay: -((i * 1.9) % 18),
    opacity: 0.2 + (seed % 35) / 100,
    drift: (i % 2 ? 1 : -1) * (14 + (seed % 42)),
  };
});

// Motion variants shared by both auth pages.
export const authStagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
};
export const authItem = {
  hidden: { opacity: 0, y: 22 },
  show: { opacity: 1, y: 0, transition: { duration: 0.8, ease: [0.22, 1, 0.36, 1] } },
};

export default function AuthScene() {
  return (
    <>
      <div className="auth__stage" aria-hidden>
        <div className="auth__stage-glow auth__stage-glow--top" />
        <div className="auth__stage-glow auth__stage-glow--left" />
        <div className="auth__stage-glow auth__stage-glow--right" />
        <div className="auth__stage-glow auth__stage-glow--floor" />
        <div className="auth__stage-fade" />
      </div>
      <div className="auth__particles" aria-hidden>
        {particles.map((p, i) => (
          <span
            key={i}
            style={{
              left: p.left,
              width: `${p.size}px`,
              height: `${p.size}px`,
              animationDuration: `${p.duration}s`,
              animationDelay: `${p.delay}s`,
              "--po": p.opacity,
              "--px": `${p.drift}px`,
            }}
          />
        ))}
      </div>
    </>
  );
}
