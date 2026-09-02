import { useCallback, useEffect, useState } from "react";
import Panel, { PanelHead } from "../../shared/Panel.jsx";
import PageHeader from "../../shared/PageHeader.jsx";
import EmptyState from "../../shared/EmptyState.jsx";
import Icon from "../../shared/Icon.jsx";
import { api } from "../../lib/api.js";
import { useAuth } from "../../shared/AuthContext.jsx";
import { cn, initials } from "../../lib/utils.js";

const ROLE_TONE = { owner: "info", producer: "ok", crew: "neutral" };
const ROLE_BLURB = {
  producer: "Can edit the schedule, budget and casting decisions, and invite others.",
  crew: "Read-only access to the production dashboard.",
};

function expiryLabel(iso) {
  const ms = Date.parse(iso) - Date.now();
  if (!Number.isFinite(ms)) return "";
  if (ms <= 0) return "expired";
  const hours = Math.round(ms / 3600000);
  if (hours < 24) return `expires in ${hours}h`;
  return `expires in ${Math.round(hours / 24)}d`;
}

// Step 2 of the team flow: mint secure invite links and manage who is on the
// production. Producers and owners only; crew never reach this route.
export default function TeamPage() {
  const { activeProjectId, canEdit, isOwner, user } = useAuth();
  const [team, setTeam] = useState(null);
  const [invites, setInvites] = useState([]);
  const [issued, setIssued] = useState(null); // shown once, never re-fetchable
  const [copied, setCopied] = useState(false);
  const [form, setForm] = useState({ role: "crew", label: "", ttl_hours: 72, max_uses: 1 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!activeProjectId) return;
    setError("");
    try {
      const t = await api.team(activeProjectId);
      setTeam(t);
      if (t.your_role === "owner" || t.your_role === "producer") {
        const { invites: list } = await api.listInvites(activeProjectId);
        setInvites(list);
      }
    } catch (e) {
      setError(String(e.message || e));
    }
  }, [activeProjectId]);

  useEffect(() => {
    load();
  }, [load]);

  async function createInvite(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setCopied(false);
    try {
      const { invite, token } = await api.createInvite({
        project_id: activeProjectId,
        role: form.role,
        label: form.label,
        ttl_hours: Number(form.ttl_hours),
        max_uses: Number(form.max_uses),
      });
      setIssued({ ...invite, url: `${window.location.origin}/join/${token}` });
      setForm((f) => ({ ...f, label: "" }));
      await load();
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  async function revoke(inviteId) {
    try {
      await api.revokeInvite(activeProjectId, inviteId);
      if (issued?.id === inviteId) setIssued(null);
      await load();
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  async function remove(userId) {
    try {
      await api.removeMember(activeProjectId, userId);
      await load();
    } catch (e) {
      setError(String(e.message || e));
    }
  }

  function copyLink() {
    navigator.clipboard?.writeText(issued.url).then(
      () => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      },
      () => setCopied(false)
    );
  }

  if (!activeProjectId) {
    return (
      <Panel>
        <EmptyState icon="groups" title="No production selected" />
      </Panel>
    );
  }

  return (
    <>
      <PageHeader
        title="Production team"
        sub={`Who can open ${team?.production?.name || activeProjectId}, and how they were invited.`}
        size="lg"
      />

      {error && (
        <div className="banner" data-tone="bad" role="alert">
          <Icon name="error" />
          <span>{error}</span>
        </div>
      )}

      <Panel className="panel--clip">
        <PanelHead title="Members" icon="groups">
          <span className="mono-data muted">{team?.members?.length ?? 0} people</span>
        </PanelHead>
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Joined</th>
                {isOwner && <th className="num">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {(team?.members || []).map((m) => (
                <tr key={m.user_id}>
                  <td>
                    <div className="avatar-cell">
                      <span className="avatar-round" aria-hidden="true">
                        {initials(m.name)}
                      </span>
                      <div>
                        <div className="name">
                          {m.name}
                          {m.is_you && <span className="muted"> · you</span>}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="muted">{m.email}</td>
                  <td>
                    <span className="status-pill" data-tone={ROLE_TONE[m.role]}>
                      <span className="dot" />
                      {m.role}
                    </span>
                  </td>
                  <td className="muted">{m.joined_at?.slice(0, 10)}</td>
                  {isOwner && (
                    <td className="num">
                      {m.role !== "owner" && (
                        <button type="button" className="btn btn--ghost" onClick={() => remove(m.user_id)}>
                          <Icon name="person_remove" />
                          Remove
                        </button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {canEdit && (
        <>
          <Panel className="panel--pad">
            <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
              <Icon name="person_add" />
              Invite a team member
            </h3>

            {issued && (
              <div className="invite-issued">
                <div className="row row--tight" style={{ marginBottom: 8 }}>
                  <Icon name="key" style={{ color: "var(--status-success)" }} />
                  <strong className="body-sm">Invite link ready — copy it now</strong>
                </div>
                <p className="body-sm muted" style={{ marginBottom: 10 }}>
                  This is the only time the link is shown. It is single-use by default and we store only a
                  fingerprint of it, so it cannot be recovered later — revoke and reissue if it goes missing.
                </p>
                <div className="invite-link">
                  <code>{issued.url}</code>
                  <button type="button" className="btn btn--tonal" onClick={copyLink}>
                    <Icon name={copied ? "check" : "content_copy"} />
                    {copied ? "Copied" : "Copy"}
                  </button>
                </div>
              </div>
            )}

            <form className="form-grid" onSubmit={createInvite} style={{ marginTop: issued ? 20 : 0 }}>
              <label className="field">
                <span className="mono-label">Role</span>
                <div className="select-wrap">
                  <select
                    className="select"
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                  >
                    <option value="crew">Crew — read only</option>
                    <option value="producer">Producer — can edit</option>
                  </select>
                  <Icon name="arrow_drop_down" />
                </div>
              </label>
              <label className="field">
                <span className="mono-label">Label (optional)</span>
                <input
                  className="input"
                  placeholder="1st AD"
                  value={form.label}
                  onChange={(e) => setForm({ ...form, label: e.target.value })}
                />
              </label>
              <label className="field">
                <span className="mono-label">Expires in (hours)</span>
                <input
                  className="input"
                  type="number"
                  min="1"
                  max="720"
                  value={form.ttl_hours}
                  onChange={(e) => setForm({ ...form, ttl_hours: e.target.value })}
                />
              </label>
              <label className="field">
                <span className="mono-label">Max uses</span>
                <input
                  className="input"
                  type="number"
                  min="1"
                  max="50"
                  value={form.max_uses}
                  onChange={(e) => setForm({ ...form, max_uses: e.target.value })}
                />
              </label>
              <button type="submit" className="btn btn--primary" disabled={busy}>
                <Icon name={busy ? "progress_activity" : "link"} className={busy ? "spin" : undefined} />
                {busy ? "Generating…" : "Generate invite"}
              </button>
            </form>
            <p className="body-sm muted" style={{ marginTop: 12 }}>
              {ROLE_BLURB[form.role]}
            </p>
          </Panel>

          <Panel className="panel--clip">
            <PanelHead title="Invites" icon="mail">
              <span className="mono-data muted">{invites.filter((i) => i.active).length} active</span>
            </PanelHead>
            {invites.length === 0 ? (
              <EmptyState icon="mail" title="No invites yet">
                Generate one above to add your director and crew.
              </EmptyState>
            ) : (
              <div className="table-scroll">
                <table className="data">
                  <thead>
                    <tr>
                      <th>Label</th>
                      <th>Role</th>
                      <th>Status</th>
                      <th>Uses</th>
                      <th className="num">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invites.map((i) => (
                      <tr key={i.id} className={cn(!i.active && "dimmed")}>
                        <td>{i.label || <span className="muted">untitled</span>}</td>
                        <td>
                          <span className="status-pill" data-tone={ROLE_TONE[i.role]}>
                            <span className="dot" />
                            {i.role}
                          </span>
                        </td>
                        <td>
                          <span
                            className="status-pill"
                            data-tone={i.active ? "ok" : i.revoked ? "bad" : "neutral"}
                          >
                            <span className="dot" />
                            {i.revoked ? "revoked" : i.expired ? "expired" : i.active ? expiryLabel(i.expires_at) : "used up"}
                          </span>
                        </td>
                        <td className="muted">
                          {i.uses} / {i.max_uses}
                        </td>
                        <td className="num">
                          {i.active && (
                            <button type="button" className="btn btn--ghost" onClick={() => revoke(i.id)}>
                              <Icon name="block" />
                              Revoke
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}

      {!canEdit && (
        <Panel className="panel--pad">
          <p className="muted body-sm">
            You're on this production as <strong>{team?.your_role}</strong>. Only producers and the owner can
            invite or remove team members.
          </p>
        </Panel>
      )}
    </>
  );
}
