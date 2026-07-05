import { useEffect, useState } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";

/** Pink dot that trails the cursor — desktop pointers only. */
export default function CursorDot() {
  const [enabled, setEnabled] = useState(false);
  const x = useMotionValue(-40);
  const y = useMotionValue(-40);
  const sx = useSpring(x, { stiffness: 220, damping: 24, mass: 0.6 });
  const sy = useSpring(y, { stiffness: 220, damping: 24, mass: 0.6 });

  useEffect(() => {
    if (!window.matchMedia("(pointer: fine)").matches) return;
    setEnabled(true);
    const move = (e) => {
      x.set(e.clientX + 14);
      y.set(e.clientY + 10);
    };
    window.addEventListener("pointermove", move);
    return () => window.removeEventListener("pointermove", move);
  }, [x, y]);

  if (!enabled) return null;

  return (
    <motion.div
      aria-hidden
      style={{
        position: "fixed",
        left: 0,
        top: 0,
        x: sx,
        y: sy,
        width: 13,
        height: 13,
        borderRadius: "50%",
        background: "var(--pink-strong)",
        pointerEvents: "none",
        zIndex: 100,
      }}
    />
  );
}
