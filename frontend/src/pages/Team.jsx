import { useCallback, useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import ConsoleShell from "../components/ConsoleShell";
import Icon from "../components/Icon";
import { apiJson, ApiError } from "../lib/api";
import { canManageTeam, roleLabel, useAuth } from "../lib/auth";
import "./Team.css";

const PLATFORM_ROLES = [
  "hospital_admin",
  "hospital_node",
  "clinic_user",
  "research_partner",
  "auditor",
  "platform_admin",
];
const HOSPITAL_ADMIN_ROLES = ["hospital_node", "clinic_user"];

function inviteLink(token) {
  return `${window.location.origin}/register?token=${token}`;
}

export default function Team() {
  const { user, token } = useAuth();
  const isPlatform = user?.role === "platform_admin";
  const mayView = canManageTeam(user?.role);

  const [requests, setRequests] = useState([]);
  const [invitations, setInvitations] = useState([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [invs, reqs] = await Promise.all([
        apiJson("/auth/invitations", {}, token),
        isPlatform ? apiJson("/auth/access-requests?status=pending", {}, token) : Promise.resolve([]),
      ]);
      setInvitations(invs);
      setRequests(reqs);
      setError("");
    } catch {
      setError("Could not load team data. Is the backend running?");
    }
  }, [token, isPlatform]);

  useEffect(() => {
    if (!mayView || !token) return undefined;
    void refresh();
  }, [mayView, token, refresh]);

  // Existing orgs the admin has seen (derived from invitations) for the org picker.
  const knownOrgs = useMemo(() => {
    const map = new Map();
    for (const inv of invitations) {
      if (inv.org_id && !map.has(inv.org_id)) map.set(inv.org_id, inv.org_name || inv.org_id);
    }
    return [...map.entries()].map(([id, name]) => ({ id, name }));
  }, [invitations]);

  async function onApprove(id) {
    try {
      const res = await apiJson(`/auth/access-requests/${id}/approve`, { method: "POST" }, token);
      setNotice(
        res.email_sent
          ? `Approved — invitation emailed to ${res.invitation.email}.`
          : `Approved — copy the invite link for ${res.invitation.email}: ${inviteLink(res.invitation.token)}`
      );
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Approval failed.");
    }
  }

  async function onReject(id) {
    try {
      await apiJson(`/auth/access-requests/${id}/reject`, {
        method: "POST",
        body: JSON.stringify({ reason: "" }),
      }, token);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Rejection failed.");
    }
  }

  async function onRevoke(id) {
    try {
      await apiJson(`/auth/invitations/${id}/revoke`, { method: "POST" }, token);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Revoke failed.");
    }
  }

  async function copyLink(tok) {
    try {
      await navigator.clipboard.writeText(inviteLink(tok));
      setNotice("Invite link copied to clipboard.");
    } catch {
      setNotice(inviteLink(tok));
    }
  }

  return (
    <ConsoleShell
      here="Team"
      title="Team &"
      titleEm="Access"
      caption="Review organization access requests and invite people into your organization."
    >
      {!mayView ? (
        <div className="panel diag__deny">
          <Icon name="lock" size={18} />
          <div>
            <b>Team management is limited to administrators.</b>
            <p>Platform admins review access requests; organization admins invite their own members.</p>
          </div>
        </div>
      ) : (
        <div className="team">
          {(error || notice) && (
            <div className={`team__flash ${error ? "is-error" : ""}`}>
              {error || notice}
            </div>
          )}

          {isPlatform && (
            <AccessRequests requests={requests} onApprove={onApprove} onReject={onReject} />
          )}

          <InvitePanel
            token={token}
            isPlatform={isPlatform}
            knownOrgs={knownOrgs}
            onCreated={(msg) => {
              setNotice(msg);
              void refresh();
            }}
            onError={setError}
          />

          <InvitationsList invitations={invitations} onRevoke={onRevoke} onCopy={copyLink} />
        </div>
      )}
    </ConsoleShell>
  );
}

function AccessRequests({ requests, onApprove, onReject }) {
  return (
    <motion.section
      className="panel team__panel"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="panel__head">
        <div>
          <h3>Access requests</h3>
          <span className="panel__caption">{requests.length} pending review</span>
        </div>
      </div>
      {requests.length === 0 ? (
        <p className="nodes__empty">No pending requests.</p>
      ) : (
        <div className="team__list">
          {requests.map((req) => (
            <div key={req.id} className="team__row">
              <div className="team__mid">
                <b>{req.organization_name}</b>
                <span>
                  {req.organization_type} · {req.contact_name} · {req.email}
                  {req.message ? ` · "${req.message}"` : ""}
                </span>
              </div>
              <div className="team__actions">
                <button className="team__btn team__btn--ok" onClick={() => onApprove(req.id)}>
                  <Icon name="check" size={14} /> Approve
                </button>
                <button className="team__btn team__btn--ghost" onClick={() => onReject(req.id)}>
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.section>
  );
}

function InvitePanel({ token, isPlatform, knownOrgs, onCreated, onError }) {
  const roles = isPlatform ? PLATFORM_ROLES : HOSPITAL_ADMIN_ROLES;
  const [email, setEmail] = useState("");
  const [role, setRole] = useState(roles[0]);
  const [orgMode, setOrgMode] = useState("existing"); // platform_admin only
  const [orgId, setOrgId] = useState("");
  const [newOrgName, setNewOrgName] = useState("");
  const [newOrgType, setNewOrgType] = useState("hospital");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const body = { email, role };
      if (isPlatform) {
        if (orgMode === "new") {
          body.new_org = { name: newOrgName, type: newOrgType };
        } else if (orgId) {
          body.org_id = orgId;
        }
        // else: no org → backend defaults platform_admin/auditor into the platform org
      }
      const res = await apiJson("/auth/invitations", { method: "POST", body: JSON.stringify(body) }, token);
      onCreated(
        res.email_sent
          ? `Invitation emailed to ${res.invitation.email}.`
          : `Invited ${res.invitation.email}. Copy the link below to share it.`
      );
      setEmail("");
      setNewOrgName("");
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Could not create the invitation.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.section
      className="panel team__panel"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="panel__head">
        <div>
          <h3>Invite a member</h3>
          <span className="panel__caption">
            {isPlatform ? "Any role, into any organization" : "Your organization only"}
          </span>
        </div>
      </div>
      <form className="team__form" onSubmit={onSubmit}>
        <div className="team__form-row">
          <label className="team__field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="person@org.example"
              required
            />
          </label>
          <label className="team__field">
            <span>Role</span>
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              {roles.map((r) => (
                <option key={r} value={r}>{roleLabel(r)}</option>
              ))}
            </select>
          </label>
        </div>

        {isPlatform && (
          <div className="team__form-row">
            <label className="team__field">
              <span>Organization</span>
              <select value={orgMode} onChange={(e) => setOrgMode(e.target.value)}>
                <option value="existing">Existing organization</option>
                <option value="new">Create new organization</option>
              </select>
            </label>
            {orgMode === "new" ? (
              <>
                <label className="team__field">
                  <span>New org name</span>
                  <input value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} placeholder="Downtown Clinic" required />
                </label>
                <label className="team__field">
                  <span>Org type</span>
                  <select value={newOrgType} onChange={(e) => setNewOrgType(e.target.value)}>
                    <option value="hospital">Hospital</option>
                    <option value="clinic">Clinic</option>
                    <option value="research">Research</option>
                  </select>
                </label>
              </>
            ) : (
              <label className="team__field">
                <span>Pick / paste org id</span>
                <input
                  list="team-orgs"
                  value={orgId}
                  onChange={(e) => setOrgId(e.target.value)}
                  placeholder="org_… (blank = platform org)"
                />
                <datalist id="team-orgs">
                  {knownOrgs.map((o) => (
                    <option key={o.id} value={o.id}>{o.name}</option>
                  ))}
                </datalist>
              </label>
            )}
          </div>
        )}

        <button type="submit" className="btn btn-primary team__submit" disabled={busy}>
          {busy ? "Inviting…" : "Send invitation"}
        </button>
      </form>
    </motion.section>
  );
}

function InvitationsList({ invitations, onRevoke, onCopy }) {
  return (
    <motion.section
      className="panel team__panel"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.7, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
    >
      <div className="panel__head">
        <div>
          <h3>Invitations</h3>
          <span className="panel__caption">{invitations.length} total</span>
        </div>
      </div>
      {invitations.length === 0 ? (
        <p className="nodes__empty">No invitations yet.</p>
      ) : (
        <div className="team__list">
          {invitations.map((inv) => (
            <div key={inv.id} className="team__row">
              <div className="team__mid">
                <b>{inv.email}</b>
                <span>
                  {roleLabel(inv.role)} · {inv.org_name || inv.org_id}
                </span>
              </div>
              <span className={`team__status team__status--${inv.status}`}>{inv.status}</span>
              <div className="team__actions">
                {inv.status === "pending" && (
                  <>
                    <button className="team__btn team__btn--ghost" onClick={() => onCopy(inv.token)}>
                      Copy link
                    </button>
                    <button className="team__btn team__btn--ghost" onClick={() => onRevoke(inv.id)}>
                      Revoke
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.section>
  );
}
