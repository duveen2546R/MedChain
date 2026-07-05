const paths = {
  hospital: (
    <>
      <path d="M4 21V8l8-4 8 4v13" />
      <path d="M9 21v-5h6v5" />
      <path d="M12 8.5v3M10.5 10h3" />
    </>
  ),
  doctor: (
    <>
      <circle cx="12" cy="7" r="3.2" />
      <path d="M5.5 21a6.5 6.5 0 0 1 13 0" />
      <path d="M12 10.2V13a3 3 0 0 0 3 3" />
    </>
  ),
  research: (
    <>
      <path d="M9 3v6l-4.5 8A2 2 0 0 0 6.3 20h11.4a2 2 0 0 0 1.8-3L15 9V3" />
      <path d="M8 3h8" />
    </>
  ),
  patient: (
    <>
      <path d="M20.8 5.6a4.4 4.4 0 0 0-7.8-2.4A4.4 4.4 0 0 0 5.2 5.6c0 4.4 5.6 8 6.8 8.7 1.2-.7 6.8-4.3 6.8-8.7Z" />
      <path d="M2 15h4l1.5-2.5L10 18l2-4 1.5 1H22" />
    </>
  ),
  lock: (
    <>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </>
  ),
  chain: (
    <>
      <rect x="3" y="9" width="6" height="6" rx="1.5" />
      <rect x="15" y="9" width="6" height="6" rx="1.5" />
      <path d="M9 12h6" />
    </>
  ),
  brain: (
    <>
      <path d="M9.5 4a2.5 2.5 0 0 0-2.4 3.2A3 3 0 0 0 6 12a3 3 0 0 0 1.5 5.2A2.5 2.5 0 0 0 12 18V5.5A1.5 1.5 0 0 0 10.5 4Z" />
      <path d="M14.5 4A2.5 2.5 0 0 1 17 6.5v0a3 3 0 0 1 1 5.5 3 3 0 0 1-1.5 5.2A2.5 2.5 0 0 1 12 18" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3 5 6v5c0 4.4 3 8 7 10 4-2 7-5.6 7-10V6Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  route: (
    <>
      <circle cx="6" cy="18" r="2.5" />
      <circle cx="18" cy="6" r="2.5" />
      <path d="M8.5 17H14a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6" />
    </>
  ),
  check: <path d="m5 12 4.5 4.5L19 7" />,
  arrow: <path d="M5 12h14m-6-6 6 6-6 6" />,
  spark: (
    <>
      <path d="M12 3v4m0 10v4m9-9h-4M7 12H3" />
      <path d="M12 8a4 4 0 0 0 4 4 4 4 0 0 0-4 4 4 4 0 0 0-4-4 4 4 0 0 0 4-4Z" />
    </>
  ),
};

export default function Icon({ name, size = 22 }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name] ?? paths.spark}
    </svg>
  );
}
