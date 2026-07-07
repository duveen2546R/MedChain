import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { AnimatePresence, animate, motion } from "framer-motion";
import Icon from "../components/Icon";
import ConsoleTabs from "../components/ConsoleTabs";
import { apiJson } from "../lib/api";
import { useFederatedBackend } from "../lib/useFederatedBackend";
import { canRunRounds, roleLabel, useAuth } from "../lib/auth";
import NewObjective from "../components/NewObjective";
import "./Dashboard.css";

const statusMeta = {
  idle: { label: "Idle", cls: "badge--idle", live: false },
  training: { label: "Training", cls: "badge--training", live: true },
  submitted: { label: "Submitting", cls: "badge--submitted", live: true },
  validated: { label: "Verified", cls: "badge--validated", live: false },
  rejected: { label: "Rejected", cls: "badge--rejected", live: false },
};

const kpiStagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.07, delayChildren: 0.15 } },
};
const kpiItem = {
  hidden: { opacity: 0, y: 20 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.22, 1, 0.36, 1] } },
};

/* Animated count-up that tweens between value changes without re-rendering. */
function AnimatedNumber({ value, decimals = 0, locale = false }) {
  const ref = useRef(null);
  const prev = useRef(0);
  useEffect(() => {
    const node = ref.current;
    if (!node || !Number.isFinite(value)) return undefined;
    const from = prev.current;
    prev.current = value;
    const fmt = (v) =>
      locale ? Math.round(v).toLocaleString() : v.toFixed(decimals);
    if (from === value) {
      node.textContent = fmt(value);
      return undefined;
    }
    const controls = animate(from, value, {
      duration: 1.1,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => {
        node.textContent = fmt(v);
      },
    });
    return () => controls.stop();
  }, [value, decimals, locale]);
  return <span ref={ref} className="tnum">0</span>;
}

/* Tiny inline trend line for KPI cards. */
function Sparkline({ values, w = 104, h = 32 }) {
  if (!values || values.length < 2) return null;
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const span = hi - lo || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - 3 - ((v - lo) / span) * (h - 6);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg className="spark" viewBox={`0 0 ${w} ${h}`} aria-hidden>
      <polyline points={pts} />
    </svg>
  );
}

/* Circular accuracy gauge for the operations panel. */
function Gauge({ value }) {
  const R = 52;
  const C = 2 * Math.PI * R;
  const frac = Math.max(0, Math.min(1, (value ?? 0) / 100));
  return (
    <div className="gauge">
      <svg viewBox="0 0 120 120" aria-hidden>
        <circle className="gauge__track" cx="60" cy="60" r={R} />
        <motion.circle
          className="gauge__fill"
          cx="60"
          cy="60"
          r={R}
          strokeDasharray={C}
          initial={{ strokeDashoffset: C }}
          animate={{ strokeDashoffset: C * (1 - frac) }}
          transition={{ duration: 1.3, ease: [0.22, 1, 0.36, 1] }}
          transform="rotate(-90 60 60)"
        />
      </svg>
      <div className="gauge__center">
        <b className="tnum">{value == null ? "—" : <AnimatedNumber value={value} decimals={1} />}</b>
        <span>reported %</span>
      </div>
    </div>
  );
}

/* Catmull-Rom → bezier so the accuracy line curves smoothly. */
function smoothPath(pts) {
  if (pts.length < 2) return "";
  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < pts.length - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(pts.length - 1, i + 2)];
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += ` C ${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }
  return d;
}

const sceneParticles = Array.from({ length: 10 }, (_, i) => ({
  left: `${(i * 47 + 13) % 100}%`,
  size: 2 + (i % 2),
  duration: 18 + ((i * 5) % 14),
  delay: -((i * 3.1) % 20),
  opacity: 0.14 + ((i * 7) % 16) / 100,
}));

export default function Dashboard() {
  const service = useFederatedBackend();
  const { user, token, logout } = useAuth();
  const navigate = useNavigate();
  const role = user?.role;
  const mayRun = canRunRounds(role);
  const mayManageChain = role === "platform_admin";
  const mayViewChain = ["platform_admin", "auditor", "research_partner"].includes(role);
  const latest = service.versions[service.versions.length - 1];
  const first = service.versions[0];

  // UI-only state: node search + notifications popover.
  const [query, setQuery] = useState("");
  const [alertsOpen, setAlertsOpen] = useState(false);

  // Compact chain explorer for audit-capable roles.
  const [blocks, setBlocks] = useState([]);
  useEffect(() => {
    if (!mayViewChain || !token) return undefined;
    let active = true;
    const fetchBlocks = async () => {
      try {
        const data = await apiJson("/blockchain/blocks?limit=8", {}, token);
        if (active) setBlocks(data);
      } catch {
        /* explorer panel simply stays empty */
      }
    };
    void fetchBlocks();
    const id = window.setInterval(fetchBlocks, 10000);
    return () => {
      active = false;
      window.clearInterval(id);
    };
  }, [mayViewChain, token]);

  // Remember each node's last reputation so score changes show a delta.
  const repTrack = useRef({});
  service.hospitals.forEach((h) => {
    const entry = repTrack.current[h.id];
    if (!entry) {
      repTrack.current[h.id] = { value: h.reputation, delta: 0 };
    } else if (entry.value !== h.reputation) {
      repTrack.current[h.id] = { value: h.reputation, delta: h.reputation - entry.value };
    }
  });

  function onLogout() {
    logout();
    navigate("/");
  }

  /* ---------- derived, display-only data ---------- */
  const received = service.submissionsReceived;
  const required = service.submissionsRequired;
  const failedRound = service.currentRoundStatus === "failed";
  const delta = latest && first ? latest.accuracy - first.accuracy : null;
  const registeredCount = service.hospitals.filter((h) => h.blockchain_registered).length;
  const pendingRegs = service.hospitals.filter((h) => h.wallet_address && !h.blockchain_registered);

  const q = query.trim().toLowerCase();
  const filteredHospitals = q
    ? service.hospitals.filter((h) =>
        [h.id, h.name, h.specialty, h.region].some((f) => f && f.toLowerCase().includes(q)),
      )
    : service.hospitals;

  const alerts = [];
  if (!service.backendConnected) alerts.push({ tone: "err", text: "Backend unreachable — showing last known state." });
  if (failedRound) alerts.push({ tone: "err", text: `Round ${service.round}: blockchain recording failed.` });
  pendingRegs.forEach((h) => alerts.push({ tone: "warn", text: `${h.name} is awaiting on-chain registration.` }));
  if (service.running) alerts.push({ tone: "info", text: `Round ${service.round} active — ${received}/${required} updates received.` });

  const collecting = service.running && received < required;
  const aggregating = service.running && required > 0 && received >= required;
  const steps = [
    {
      key: "init",
      label: "Round initiated",
      meta: service.currentRoundId ? `Round ${service.round} in flight` : service.round > 0 ? `Last round ${service.round}` : "Awaiting first round",
      state: service.currentRoundId ? "done" : "idle",
    },
    {
      key: "collect",
      label: "Collecting hospital updates",
      meta: required > 0 ? `${received} of ${required} received` : "No active selection",
      state: collecting ? "active" : received > 0 || (!service.running && service.round > 0) ? "done" : "idle",
    },
    {
      key: "agg",
      label: "Federated aggregation",
      meta: aggregating ? "Combining verified updates" : latest ? `Latest release ${latest.version}` : "Pending first release",
      state: aggregating ? "active" : latest ? "done" : "idle",
    },
    {
      key: "chain",
      label: "On-chain record",
      meta: failedRound ? "Recording failed — retry available" : `${service.blockchainTransactions} confirmed receipts`,
      state: failedRound ? "error" : service.blockchainTransactions > 0 ? "done" : "idle",
    },
  ];

  const feed = [
    latest && { icon: "layers", text: `Model ${latest.version} aggregated from ${latest.contributors} contributor${latest.contributors === 1 ? "" : "s"} at ${latest.accuracy}% reported accuracy.` },
    service.currentRoundId && { icon: "inbox", text: `${received} of ${required} hospital updates received for round ${service.round}.` },
    { icon: "chain", text: service.blockchainConnected ? `Chain ${service.blockchainChainId} connected — ${service.blockchainTransactions} contribution receipts.` : "Blockchain connection not established." },
    { icon: "hospital", text: `${registeredCount} of ${service.hospitals.length} consortium nodes registered on-chain.` },
  ].filter(Boolean);

  /* ---------- chart geometry ---------- */
  const chartW = 620;
  const chartH = 190;
  const accs = service.versions.map((v) => v.accuracy);
  const evals = service.versions.map((v) => v.evaluated_accuracy).filter((v) => v != null);
  const allValues = [...accs, ...evals];
  const lo = allValues.length ? Math.max(0, Math.floor(Math.min(...allValues)) - 5) : 0;
  const hi = allValues.length ? Math.min(100, Math.ceil(Math.max(...allValues)) + 3) : 100;
  const xAt = (i) =>
    service.versions.length === 1 ? chartW / 2 : (i / (service.versions.length - 1)) * chartW;
  const yAt = (value) => chartH - ((value - lo) / (hi - lo || 1)) * chartH;
  const points = service.versions.map((v, i) => ({ x: xAt(i), y: yAt(v.accuracy), v }));
  const evalPoints = service.versions
    .map((v, i) => (v.evaluated_accuracy != null ? { x: xAt(i), y: yAt(v.evaluated_accuracy), v } : null))
    .filter(Boolean);
  const linePath = smoothPath(points);
  const evalPath = smoothPath(evalPoints);
  const areaPath = points.length > 1 ? `${linePath} L ${chartW} ${chartH} L 0 ${chartH} Z` : "";

  return (
    <main className="dash">
      {/* ambient scene */}
      <div className="dash__scene" aria-hidden>
        <div className="dash__scene-glow dash__scene-glow--top" />
        <div className="dash__orb dash__orb--a" />
        <div className="dash__orb dash__orb--b" />
        <div className="dash__orb dash__orb--c" />
        <div className="dash__particles">
          {sceneParticles.map((p, i) => (
            <span
              key={i}
              style={{
                left: p.left,
                width: `${p.size}px`,
                height: `${p.size}px`,
                animationDuration: `${p.duration}s`,
                animationDelay: `${p.delay}s`,
                "--po": p.opacity,
              }}
            />
          ))}
        </div>
        <div className="dash__noise" />
      </div>

      <div className="container dash__inner">
        {/* ============ sticky glass navigation ============ */}
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
            <span className="dash__crumb-here">Console</span>
          </nav>

          <label className="dash__search">
            <Icon name="search" size={15} />
            <input
              type="search"
              placeholder="Search hospital nodes…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Search hospital nodes"
            />
          </label>

          <div className="dash__nav-right">
            <span className={`dash__livepill ${service.backendConnected ? "is-live" : "is-down"}`}>
              <i />
              {service.backendConnected ? "Live" : "Offline"}
            </span>

            <div className="dash__bellwrap">
              <button
                className="dash__iconbtn"
                onClick={() => setAlertsOpen((v) => !v)}
                aria-expanded={alertsOpen}
                aria-label={`Notifications (${alerts.length})`}
              >
                <Icon name="bell" size={17} />
                {alerts.length > 0 && <span className="dash__bellbadge tnum">{alerts.length}</span>}
              </button>
              <AnimatePresence>
                {alertsOpen && (
                  <motion.div
                    className="dash__pop"
                    initial={{ opacity: 0, y: 8, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 6, scale: 0.98 }}
                    transition={{ duration: 0.25, ease: [0.22, 1, 0.36, 1] }}
                  >
                    <b className="dash__pop-title">Notifications</b>
                    {alerts.length === 0 ? (
                      <p className="dash__pop-empty">All systems nominal.</p>
                    ) : (
                      alerts.map((a, i) => (
                        <p key={i} className={`dash__pop-item tone-${a.tone}`}>
                          <i /> {a.text}
                        </p>
                      ))
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {user && (
              <div className="dash__user">
                <span className="dash__user-avatar">{(user.name || user.email || "?").charAt(0).toUpperCase()}</span>
                <span className="dash__user-meta">
                  <b>{user.name || user.email}</b>
                  <span>{roleLabel(role)}</span>
                </span>
                <button className="dash__iconbtn" onClick={onLogout} title="Sign out" aria-label="Sign out">
                  <Icon name="logout" size={16} />
                </button>
              </div>
            )}
          </div>
        </motion.header>

        <ConsoleTabs />

        {/* ============ page heading ============ */}
        <motion.section
          className="dash__hero"
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.08, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="dash__hero-copy">
            <span className="eyebrow">
              <span className="dot" /> {service.backendConnected ? "Live backend · connected" : "Backend unavailable"}
            </span>
            <h1 className="dash__title">Federated Training Console</h1>
            <p className="dash__phase">
              <span className={`dash__pulse ${service.running ? "is-on" : ""}`} />
              {service.phase}
            </p>
          </div>

          <div className="dash__hero-side">
            <span className={`dash__roundpill ${service.running ? "is-active" : ""}`}>
              <i />
              Round {service.round} · {service.running ? "Active" : "Standby"}
            </span>
            <motion.button
              whileTap={{ scale: 0.97 }}
              className="btn btn-primary dash__cta"
              onClick={service.runRound}
              disabled={service.running || !mayRun || !service.backendConnected || Boolean(service.pendingAction)}
              title={mayRun ? "Start a training round" : "Requires a Hospital Admin or Platform Admin role"}
            >
              {service.pendingAction === "round:create" ? "Starting" : service.running ? "Round active" : "Start Round"}
              {!service.running && <Icon name="arrow" size={16} />}
            </motion.button>
            {!mayRun && (
              <span className="dash__rolehint">
                Signed in as {roleLabel(role)} — this role has read-only access to the console.
              </span>
            )}
          </div>
        </motion.section>

        {mayRun && <NewObjective />}

        {/* ============ KPI cards ============ */}
        <motion.section className="kpi-row" variants={kpiStagger} initial="hidden" animate="show">
          <motion.div variants={kpiItem} className="kpi">
            <div className="kpi__top">
              <span className="kpi__label">Reported accuracy</span>
              <span className="kpi__icon"><Icon name="pulse" size={16} /></span>
            </div>
            <div className="kpi__valrow">
              <b className="kpi__value gradient-text">
                {latest ? <><AnimatedNumber value={latest.accuracy} decimals={1} />%</> : "—"}
              </b>
              {delta != null && (
                <span className={`kpi__trend ${delta >= 0 ? "is-up" : "is-down"}`}>
                  {delta >= 0 ? "▲" : "▼"} {Math.abs(delta).toFixed(2)}%
                </span>
              )}
            </div>
            <div className="kpi__foot">
              <span className="kpi__sub">
                {service.evaluatedAccuracy != null
                  ? `digital-twin evaluated ${service.evaluatedAccuracy}%`
                  : latest ? "across aggregated versions" : "No model aggregated yet"}
              </span>
              <Sparkline values={accs} />
            </div>
          </motion.div>

          <motion.div variants={kpiItem} className="kpi">
            <div className="kpi__top">
              <span className="kpi__label">Model version</span>
              <span className="kpi__icon"><Icon name="layers" size={16} /></span>
            </div>
            <div className="kpi__valrow">
              <b className="kpi__value">{latest?.version || "—"}</b>
            </div>
            <div className="kpi__foot">
              <span className="kpi__sub">Round {service.round} · {service.versions.length} release{service.versions.length === 1 ? "" : "s"}</span>
              <span className="kpi__dots">
                {service.versions.slice(-6).map((v) => (
                  <i key={v.version} title={`${v.version} · ${v.accuracy}%`} />
                ))}
              </span>
            </div>
          </motion.div>

          <motion.div variants={kpiItem} className="kpi">
            <div className="kpi__top">
              <span className="kpi__label">Round submissions</span>
              <span className="kpi__icon"><Icon name="inbox" size={16} /></span>
            </div>
            <div className="kpi__valrow">
              <b className="kpi__value">
                <AnimatedNumber value={received} />
                <span className="kpi__den">/{required}</span>
              </b>
            </div>
            <div className="kpi__bar">
              <motion.i
                animate={{ width: required > 0 ? `${Math.min(100, (received / required) * 100)}%` : "0%" }}
                transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
              />
            </div>
            <span className="kpi__sub">
              hospital updates received by API
              {service.rejectedSubmissions > 0 && (
                <> · <span className="kpi__reject tnum">{service.rejectedSubmissions} rejected by gate</span></>
              )}
            </span>
          </motion.div>

          <motion.div variants={kpiItem} className="kpi">
            <div className="kpi__top">
              <span className="kpi__label">On-chain records</span>
              <span className="kpi__icon"><Icon name="chain" size={16} /></span>
            </div>
            <div className="kpi__valrow">
              <b className="kpi__value"><AnimatedNumber value={service.blockchainTransactions} /></b>
            </div>
            <div className="kpi__foot">
              <span className="kpi__sub">Consortium chain {service.blockchainChainId || "—"}</span>
              <span className={`kpi__chip ${service.blockchainConnected ? "is-ok" : "is-off"}`}>
                <i /> {service.blockchainConnected ? "Connected" : "Offline"}
              </span>
            </div>
          </motion.div>
        </motion.section>

        {/* ============ main grid ============ */}
        <div className="dash__grid">
          {/* -------- hospital nodes (hero section) -------- */}
          <motion.section
            className="panel panel--nodes"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.28, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="panel__head">
              <div>
                <h3>Hospital Nodes</h3>
                <span className="panel__caption">Federated consortium members</span>
              </div>
              <span className="panel__tag">
                {q ? `${filteredHospitals.length} of ${service.hospitals.length}` : `${service.hospitals.length} in consortium`}
              </span>
            </div>

            <div className="nodes">
              {filteredHospitals.length === 0 && (
                <p className="nodes__empty">No nodes match “{query}”.</p>
              )}
              {filteredHospitals.map((h) => {
                const m = statusMeta[h.status] || statusMeta.idle;
                const health = h.reputation >= 85 ? { label: "Excellent", cls: "is-ok" } : h.reputation >= 70 ? { label: "Stable", cls: "is-mid" } : { label: "Watch", cls: "is-warn" };
                const initials = (h.name || h.id).split(" ").map((w) => w[0]).slice(0, 2).join("").toUpperCase();
                return (
                  <motion.article
                    key={h.id}
                    className={`node ${service.activeNode === h.id ? "node--active" : ""}`}
                    layout
                    whileHover={{ y: -3 }}
                    transition={{ duration: 0.25, ease: "easeOut" }}
                  >
                    <div className="node__top">
                      <div className="node__avatar" aria-hidden>{initials}</div>
                      <div className="node__meta">
                        <b>{h.name}</b>
                        <span>{h.specialty} · {h.region} · {h.samples.toLocaleString()} samples</span>
                      </div>
                      <span className={`badge ${m.cls}`}>
                        <i className={m.live ? "is-pulsing" : ""} />
                        {m.label}
                      </span>
                    </div>

                    <div className="node__chain">
                      <span className={`node__chip ${h.blockchain_registered ? "is-ok" : "is-warn"}`}>
                        <Icon name="chain" size={13} />
                        {h.blockchain_registered ? "Registered on-chain" : "Pending registration"}
                      </span>
                      {h.wallet_address && (
                        <span className="node__wallet" title={h.wallet_address}>
                          {h.wallet_address.slice(0, 8)}…{h.wallet_address.slice(-6)}
                        </span>
                      )}
                      {mayManageChain && h.wallet_address && !h.blockchain_registered && (
                        <motion.button
                          whileTap={{ scale: 0.96 }}
                          className="node__chain-btn"
                          onClick={() => service.registerHospitalOnChain(h.id)}
                          disabled={!service.backendConnected || Boolean(service.pendingAction)}
                          title="Register this hospital wallet in the consortium registry"
                        >
                          <Icon name="chain" size={13} />
                          {service.pendingAction === `hospital:${h.id}:register` ? "Registering" : "Register"}
                        </motion.button>
                      )}
                    </div>

                    <div className="node__bars">
                      <div className="node__rep">
                        <span>Reputation</span>
                        <div className="bar"><motion.i animate={{ width: `${h.reputation}%` }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} /></div>
                        <b className="tnum">
                          {h.reputation}
                          {repTrack.current[h.id]?.delta !== 0 && (
                            <span className={`node__repdelta ${repTrack.current[h.id].delta > 0 ? "is-up" : "is-down"}`}>
                              {repTrack.current[h.id].delta > 0 ? "▲" : "▼"}{Math.abs(repTrack.current[h.id].delta)}
                            </span>
                          )}
                        </b>
                      </div>
                      <span className={`node__health ${health.cls}`}><i /> {health.label}</span>
                      {h.contribution > 0 && (
                        <span className="node__contrib tnum">weight {h.contribution}%</span>
                      )}
                    </div>
                  </motion.article>
                );
              })}
            </div>
          </motion.section>

          {/* -------- live operations -------- */}
          <motion.section
            className="panel panel--ops"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.34, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="panel__head">
              <div>
                <h3>Live Operations</h3>
                <span className="panel__caption">Round pipeline &amp; system health</span>
              </div>
              <span className="panel__tag">3s sync</span>
            </div>

            <div className="ops__top">
              <Gauge value={latest?.accuracy ?? null} />
              <dl className="ops__stats">
                <div>
                  <dt>API</dt>
                  <dd className={service.backendConnected ? "is-ok" : "is-err"}>
                    <i /> {service.backendConnected ? "Connected" : "Unreachable"}
                  </dd>
                </div>
                <div>
                  <dt>Chain {service.blockchainChainId || "—"}</dt>
                  <dd className={service.blockchainConnected ? "is-ok" : "is-warn"}>
                    <i /> {service.blockchainConnected ? "Connected" : "Not connected"}
                  </dd>
                </div>
                <div>
                  <dt>Round state</dt>
                  <dd className={failedRound ? "is-err" : service.running ? "is-live" : "is-idle"}>
                    <i /> {failedRound ? "Failed" : service.running ? "Running" : "Standby"}
                  </dd>
                </div>
                <div>
                  <dt>Updates</dt>
                  <dd className="is-idle"><i /> <span className="tnum">{received}/{required || "—"}</span></dd>
                </div>
              </dl>
            </div>

            <ol className="tl">
              {steps.map((s) => (
                <li key={s.key} className={`tl__step tl__step--${s.state}`}>
                  <span className="tl__dot" />
                  <div className="tl__copy">
                    <b>{s.label}</b>
                    <span>{s.meta}</span>
                  </div>
                </li>
              ))}
            </ol>

            {mayManageChain && failedRound && service.currentRoundId && (
              <motion.button
                whileTap={{ scale: 0.96 }}
                className="ops__retry"
                onClick={service.retryRoundBlockchain}
                disabled={!service.backendConnected || Boolean(service.pendingAction)}
                title="Retry confirmed blockchain recording for the current round"
              >
                <Icon name="chain" size={14} />
                {service.pendingAction === `round:${service.currentRoundId}:retry-chain` ? "Retrying" : "Retry chain recording"}
              </motion.button>
            )}

            <div className="ops__feed">
              <b className="ops__feed-title">Activity</b>
              {feed.map((f, i) => (
                <p key={i} className="ops__feed-item">
                  <span className="ops__feed-icon"><Icon name={f.icon} size={13} /></span>
                  {f.text}
                </p>
              ))}
            </div>
          </motion.section>

          {/* -------- accuracy chart -------- */}
          <motion.section
            className="panel panel--chart"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="panel__head">
              <div>
                <h3>Accuracy History</h3>
                <span className="panel__caption">
                  <i className="chart__key chart__key--reported" /> client-reported ·{" "}
                  <i className="chart__key chart__key--evaluated" /> digital-twin evaluated
                </span>
              </div>
              <span className="panel__tag">{service.versions.length} point{service.versions.length === 1 ? "" : "s"}</span>
            </div>

            {points.length === 0 ? (
              <p className="chart__empty">No aggregated versions yet — run a round to see reported accuracy.</p>
            ) : (
              <div className="chart__wrap">
                <svg className="chart" viewBox={`0 0 ${chartW} ${chartH + 30}`} preserveAspectRatio="none">
                  <defs>
                    <linearGradient id="dashFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="rgba(243,153,179,0.3)" />
                      <stop offset="100%" stopColor="rgba(243,153,179,0.01)" />
                    </linearGradient>
                    <linearGradient id="dashStroke" x1="0" y1="0" x2="1" y2="0">
                      <stop offset="0%" stopColor="#ffd9e1" />
                      <stop offset="100%" stopColor="#f399b3" />
                    </linearGradient>
                  </defs>
                  {[0, 0.25, 0.5, 0.75, 1].map((g) => (
                    <line key={g} x1="0" x2={chartW} y1={chartH * g} y2={chartH * g} className="chart__grid" />
                  ))}
                  {areaPath && (
                    <motion.path d={areaPath} fill="url(#dashFill)" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1 }} />
                  )}
                  <motion.path
                    d={linePath}
                    fill="none"
                    stroke="url(#dashStroke)"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    initial={{ pathLength: 0 }}
                    animate={{ pathLength: 1 }}
                    transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
                  />
                  {evalPath && (
                    <motion.path
                      d={evalPath}
                      fill="none"
                      className="chart__eval"
                      strokeWidth="2"
                      strokeDasharray="6 5"
                      strokeLinecap="round"
                      initial={{ pathLength: 0 }}
                      animate={{ pathLength: 1 }}
                      transition={{ duration: 1.2, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
                    />
                  )}
                  {evalPoints.map((p) => (
                    <g key={`eval-${p.v.version}`} className="chart__pt chart__pt--eval">
                      <circle cx={p.x} cy={p.y} r="3.2" />
                      <title>{`${p.v.version} · twin-evaluated ${p.v.evaluated_accuracy}%`}</title>
                    </g>
                  ))}
                  {points.map((p) => (
                    <g key={p.v.version} className="chart__pt">
                      <circle cx={p.x} cy={p.y} r="4" />
                      <title>{`${p.v.version} · ${p.v.accuracy}% · round ${p.v.round}`}</title>
                      <text x={p.x} y={chartH + 22} textAnchor="middle">{p.v.version}</text>
                    </g>
                  ))}
                </svg>
                <div className="chart__scale tnum">
                  <span>{hi}%</span>
                  <span>{lo}%</span>
                </div>
              </div>
            )}
          </motion.section>

          {/* -------- version history -------- */}
          <motion.section
            className="panel panel--versions"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.46, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="panel__head">
              <div>
                <h3>Version History</h3>
                <span className="panel__caption">Aggregated global releases</span>
              </div>
              <span className="panel__tag">{service.versions.length} release{service.versions.length === 1 ? "" : "s"}</span>
            </div>
            <div className="versions">
              {service.versions.length === 0 && (
                <p className="nodes__empty">No releases yet.</p>
              )}
              {[...service.versions].reverse().map((v) => (
                <div className="ver" key={v.version}>
                  <span className="ver__tag">{v.version}</span>
                  <div className="ver__mid">
                    <b className="tnum">
                      {v.accuracy}%
                      {v.evaluated_accuracy != null && (
                        <span className="ver__eval tnum"> · twin {v.evaluated_accuracy}%</span>
                      )}
                    </b>
                    <span>Round {v.round} · {v.contributors} contributor{v.contributors === 1 ? "" : "s"}</span>
                  </div>
                  <div className="ver__bar">
                    <motion.i animate={{ width: `${v.accuracy}%` }} transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }} />
                  </div>
                </div>
              ))}
            </div>
          </motion.section>

          {/* -------- consortium chain explorer -------- */}
          {mayViewChain && (
            <motion.section
              className="panel panel--chain"
              initial={{ opacity: 0, y: 22 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.52, ease: [0.22, 1, 0.36, 1] }}
            >
              <div className="panel__head">
                <div>
                  <h3>Consortium Chain Explorer</h3>
                  <span className="panel__caption">Signed blocks · newest first · 10s sync</span>
                </div>
                <span className="panel__tag">height {blocks.length ? blocks[0].number : "—"}</span>
              </div>
              <div className="chainx">
                {blocks.length === 0 && <p className="nodes__empty">No blocks to display.</p>}
                {blocks.map((b) => (
                  <div className="chainx__row" key={b.id}>
                    <span className="chainx__num tnum">#{b.number}</span>
                    <div className="chainx__mid">
                      <b>{b.transactions.map((t) => t.type.replaceAll("_", " ")).join(", ") || "empty block"}</b>
                      <span title={b.hash}>
                        {b.hash.slice(0, 18)}… · {new Date(b.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                    <span className="chainx__txs tnum">{b.transactions.length} tx</span>
                  </div>
                ))}
              </div>
            </motion.section>
          )}
        </div>

        <p className="dash__foot">
          Every value on this dashboard comes from the authenticated FastAPI service. Hospital clients
          train locally and submit real model updates through the API; the backend stress-tests each one
          against the digital twin, aggregates the survivors, stores artifacts in Azure, and records every
          contribution and reputation change on the embedded consortium blockchain.
        </p>
      </div>
    </main>
  );
}
