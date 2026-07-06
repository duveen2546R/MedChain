import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import ConsoleShell from "../components/ConsoleShell";
import Icon from "../components/Icon";
import { apiJson } from "../lib/api";
import { useAuth } from "../lib/auth";

const TX_LABELS = {
  genesis: "Genesis",
  node_registered: "Node registered",
  node_activated: "Node activated",
  reputation_seeded: "Reputation seeded",
  reputation_updated: "Reputation updated",
  contribution_recorded: "Contribution recorded",
};

function shortHash(hash, head = 10, tail = 6) {
  if (!hash) return "—";
  return `${hash.slice(0, head)}…${hash.slice(-tail)}`;
}

export default function Explorer() {
  const { user, token } = useAuth();
  const mayView = ["platform_admin", "auditor", "research_partner"].includes(user?.role);

  const [verify, setVerify] = useState(null);
  const [blocks, setBlocks] = useState([]);
  const [openBlock, setOpenBlock] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [verification, blockList] = await Promise.all([
        apiJson("/blockchain/verify", {}, token),
        apiJson("/blockchain/blocks?limit=50", {}, token),
      ]);
      setVerify(verification);
      setBlocks(blockList);
      setError("");
    } catch {
      setError("Could not load the chain. Is the backend running?");
    }
  }, [token]);

  useEffect(() => {
    if (!mayView || !token) return undefined;
    void refresh();
    const id = window.setInterval(refresh, 10000);
    return () => window.clearInterval(id);
  }, [mayView, token, refresh]);

  return (
    <ConsoleShell
      here="Chain Explorer"
      title="Consortium"
      titleEm="Chain"
      caption="Every hospital registration, model contribution, and reputation change — hash-linked, ECDSA-signed, and re-verified on every backend start."
    >
      {!mayView ? (
        <div className="panel diag__deny">
          <Icon name="lock" size={18} />
          <div>
            <b>The chain explorer is limited to audit-capable roles.</b>
            <p>Platform administrators, auditors, and research partners can inspect the full block history.</p>
          </div>
        </div>
      ) : (
        <>
          <motion.section
            className="kpi-row"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.12, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="kpi">
              <div className="kpi__top"><span className="kpi__label">Integrity</span><span className="kpi__icon"><Icon name="shield" size={16} /></span></div>
              <div className="kpi__valrow">
                <b className={`kpi__value ${verify?.valid ? "gradient-text" : ""}`}>{verify ? (verify.valid ? "Verified" : "TAMPERED") : "—"}</b>
              </div>
              <span className="kpi__sub">{verify ? `re-checked ${new Date(verify.verified_at).toLocaleTimeString()}` : "loading"}</span>
            </div>
            <div className="kpi">
              <div className="kpi__top"><span className="kpi__label">Block height</span><span className="kpi__icon"><Icon name="layers" size={16} /></span></div>
              <div className="kpi__valrow"><b className="kpi__value tnum">{verify?.height ?? "—"}</b></div>
              <span className="kpi__sub">chain {verify?.chain_id ?? "—"} · {verify?.network || "medchain-consortium"}</span>
            </div>
            <div className="kpi">
              <div className="kpi__top"><span className="kpi__label">Transactions</span><span className="kpi__icon"><Icon name="chain" size={16} /></span></div>
              <div className="kpi__valrow"><b className="kpi__value tnum">{verify?.transactions ?? "—"}</b></div>
              <span className="kpi__sub">across {verify?.blocks ?? "—"} signed blocks</span>
            </div>
            <div className="kpi">
              <div className="kpi__top"><span className="kpi__label">Authority</span><span className="kpi__icon"><Icon name="lock" size={16} /></span></div>
              <div className="kpi__valrow"><b className="kpi__value kpi__value--sm" title={verify?.authority}>{shortHash(verify?.authority, 8, 6)}</b></div>
              <span className="kpi__sub">signs every block and transaction</span>
            </div>
          </motion.section>

          <motion.section
            className="panel panel--chain xplr"
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="panel__head">
              <div>
                <h3>Blocks</h3>
                <span className="panel__caption">Newest first · click a block for its signed transactions</span>
              </div>
              <span className="panel__tag">10s sync</span>
            </div>

            {error && <p className="nodes__empty">{error}</p>}
            <div className="chainx">
              {blocks.map((block) => (
                <div key={block.id} className="xplr__block">
                  <button
                    type="button"
                    className="chainx__row xplr__row"
                    onClick={() => setOpenBlock(openBlock === block.id ? null : block.id)}
                    aria-expanded={openBlock === block.id}
                  >
                    <span className="chainx__num tnum">#{block.number}</span>
                    <div className="chainx__mid">
                      <b>{block.transactions.map((tx) => TX_LABELS[tx.type] || tx.type).join(", ")}</b>
                      <span title={block.hash}>
                        {shortHash(block.hash, 16, 8)} · {new Date(block.timestamp).toLocaleString()}
                      </span>
                    </div>
                    <span className="chainx__txs tnum">{block.transactions.length} tx</span>
                  </button>
                  {openBlock === block.id && (
                    <div className="xplr__detail">
                      <div className="xplr__meta">
                        <span><b>Previous</b> {shortHash(block.previous_hash, 14, 8)}</span>
                        <span><b>Merkle root</b> {shortHash(block.merkle_root, 14, 8)}</span>
                        <span><b>Signer</b> {shortHash(block.signer, 8, 6)}</span>
                      </div>
                      {block.transactions.map((tx) => (
                        <div key={tx.tx_hash} className="xplr__tx">
                          <div className="xplr__tx-head">
                            <b>{TX_LABELS[tx.type] || tx.type}</b>
                            <span title={tx.tx_hash}>{shortHash(tx.tx_hash, 14, 8)}</span>
                          </div>
                          <pre>{JSON.stringify(tx.payload, null, 2)}</pre>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </motion.section>
        </>
      )}
    </ConsoleShell>
  );
}
