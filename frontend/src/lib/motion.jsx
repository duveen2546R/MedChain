import { motion } from "framer-motion";

/** Fade + rise on scroll into view. */
export function Reveal({
  children,
  delay = 0,
  y = 24,
  className,
}) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-80px" }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
    >
      {children}
    </motion.div>
  );
}

/** Stagger container for lists of cards. */
export const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.09 } },
};

export const staggerItem = {
  hidden: { opacity: 0, y: 22 },
  show: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.55, ease: [0.22, 1, 0.36, 1] },
  },
};
