import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import ConsoleShell from "../components/ConsoleShell";
import Icon from "../components/Icon";
import { apiJson } from "../lib/api";
import { roleLabel, useAuth } from "../lib/auth";

const TONE_BY_PREFIX = [
  ["round.blockchain.failed", "err"],
  ["round.submission.anomaly_rejected", "warn"],
  ["round.cancelled", "warn"],
  ["hospital.reputation", "info"],
  ["inference", "info"],
];

function toneFor(action) {
  const match = TONE_BY_PREFIX.find(([prefix]) => action.startsWith(prefix));
  return match ? match[1] : "ok";
}

export default function Audit() {
  const { user, token } = useAuth();
  const mayView = ["platform_admin", "auditor"].includes(user?.role);

  const [events, setEvents] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setEvents(await apiJson("/audit/events", {}, token));
      setError("");
    } catch {
      setError("Could not load audit events. Is the backend running?");
    }
  }, [token]);

  useEffect(() => {
    if (!mayView || !token) return undefined;
    void refresh();
    const id = window.setInterval(refresh, 10000);
    return () => window.clearInterval(id);
  }, [mayView, token, refresh]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const ordered = [...events].reverse();
    if (!q) return ordered;
    return ordered.filter((event) =>
      [event.action, event.resource_type, event.resource_id, event.actor_role]
        .some((field) => field && field.toLowerCase().includes(q)),
    );
  }, [events, query]);

  async function onExport() {
    setExporting(true);
    try {
      const payload = await apiJson("/compliance/exports", {}, token);
      const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `medchain-compliance-${new Date().toISOString().slice(0, 19)}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Compliance export failed. Try again.");
    } finally {
      setExporting(false);
    }
  }

  return (
    <ConsoleShell
      here="Audit Log"
      title="Audit"
      titleEm="Trail"
      caption="Every consequential action — registrations, submissions, gate rejections, reputation changes, inferences — recorded with its actor."
    >
      {!mayView ? (
        <div className="panel diag__deny">
          <Icon name="lock" size={18} />
          <div>
            <b>The audit log is limited to administrators and auditors.</b>
            <p>These roles review platform activity and produce compliance exports for regulators.</p>
          </div>
        </div>
      ) : (
        <motion.section
          className="panel panel--chain audit"
          initial={{ opacity: 0, y: 22 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.14, ease: [0.22, 1, 0.36, 1] }}
        >
          <div className="panel__head">
            <div>
              <h3>Events</h3>
              <span className="panel__caption">{events.length} recorded · newest first · 10s sync</span>
            </div>
            <div className="audit__tools">
              <label className="dash__search audit__search">
                <Icon name="search" size={14} />
                <input
                  type="search"
                  placeholder="Filter events…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  aria-label="Filter audit events"
                />
              </label>
              <motion.button
                whileTap={{ scale: 0.96 }}
                className="audit__export"
                onClick={onExport}
                disabled={exporting}
                title="Download a JSON compliance export of the full audit trail"
              >
                <Icon name="shield" size={14} />
                {exporting ? "Exporting…" : "Compliance export"}
              </motion.button>
            </div>
          </div>

          {error && <p className="nodes__empty">{error}</p>}
          <div className="audit__list">
            {filtered.length === 0 && !error && <p className="nodes__empty">No events match.</p>}
            {filtered.slice(0, 120).map((event) => (
              <div key={event.id} className="audit__row">
                <span className={`audit__dot tone-${toneFor(event.action)}`} aria-hidden />
                <div className="audit__mid">
                  <b>{event.action}</b>
                  <span>
                    {event.resource_type}
                    {event.resource_id ? ` · ${event.resource_id}` : ""}
                    {event.actor_role ? ` · by ${roleLabel(event.actor_role)}` : " · system"}
                  </span>
                </div>
                <span className="audit__time tnum">{new Date(event.created_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </motion.section>
      )}
    </ConsoleShell>
  );
}
