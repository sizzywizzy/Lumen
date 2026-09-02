import { useMemo, useState } from "react";
import Panel, { PanelFoot } from "../../shared/Panel.jsx";
import PageHeader from "../../shared/PageHeader.jsx";
import MetricCard, { MetricRow } from "../../shared/MetricCard.jsx";
import StatusBadge, { StatusBadgeSelect } from "../../shared/StatusBadge.jsx";
import { ScoreCell } from "../../shared/Meter.jsx";
import EmptyState from "../../shared/EmptyState.jsx";
import Icon from "../../shared/Icon.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { api } from "../../lib/api.js";
import { cn, initials, statusLabel } from "../../lib/utils.js";
import { STAGE_BY_PATH } from "../../shared/navigation.js";

const CSV_COLUMNS = ["rank", "id", "name", "role_id", "status", "audition", "hype", "pr", "budget", "composite"];

// The funnel a producer can move a candidate through by hand. Mirrors
// CandidateStatus in the backend contract.
const CASTING_STATUSES = ["SOURCING", "SCREENING", "LOCKED", "FLAGGED_ACTION_REQUIRED", "DISQUALIFIED"];
const NEEDS_REASON = ["DISQUALIFIED"];

function toCsv(rows) {
  const escape = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return [CSV_COLUMNS.join(","), ...rows.map((r) => CSV_COLUMNS.map((c) => escape(r[c])).join(","))].join("\n");
}

// Phase I & II — the casting leaderboard. Ranking, scores and disqualifications
// all come from GlobalState.candidates; the layout is the Stitch leaderboard.
export default function CastingView() {
  const { state, running, canEdit, projectId, applyCandidateUpdate } = useProject();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [savingId, setSavingId] = useState(null);
  const [statusError, setStatusError] = useState("");

  // Persist to the shared GlobalState so the whole team sees the decision,
  // then reflect the server's own copy of the row in the UI immediately.
  async function changeStatus(candidate, nextStatus, reason) {
    setSavingId(candidate.id);
    setStatusError("");
    try {
      const res = await api.setCandidateStatus(projectId, candidate.id, nextStatus, reason);
      applyCandidateUpdate(res.candidate, res.casting_status, res.event_log);
    } catch (e) {
      setStatusError(`Could not update ${candidate.name}: ${e.message || e}`);
    } finally {
      setSavingId(null);
    }
  }

  const ranked = useMemo(() => {
    if (!state?.candidates) return [];
    return [...state.candidates].sort((a, b) => (b.scores.composite ?? -1) - (a.scores.composite ?? -1));
  }, [state]);

  const statuses = useMemo(() => [...new Set(ranked.map((c) => c.status))], [ranked]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return ranked.filter((c) => {
      if (statusFilter !== "ALL" && c.status !== statusFilter) return false;
      if (!q) return true;
      return `${c.name} ${c.role_id}`.toLowerCase().includes(q);
    });
  }, [ranked, query, statusFilter]);

  const disqualified = ranked.filter((c) => c.status === "DISQUALIFIED");
  const locked = ranked.filter((c) => c.status === "LOCKED").length;
  const screening = ranked.filter((c) => c.status === "SCREENING").length;

  function exportCsv() {
    const rows = visible.map((c, i) => ({
      rank: i + 1,
      id: c.id,
      name: c.name,
      role_id: c.role_id,
      status: c.status,
      audition: c.scores.audition ?? "",
      hype: c.scores.hype ?? "",
      pr: c.scores.pr ?? "",
      budget: c.scores.budget ?? "",
      composite: c.scores.composite ?? "",
    }));
    const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${state?.project_id || "cinenode"}-casting-leaderboard.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <PageHeader
        title="Casting Leaderboard"
        sub={`Real-time candidate evaluation for ${state?.project_id || "this project"}. Ranks are sorted on the composite of audition, hype, PR and budget fit.`}
        meta={STAGE_BY_PATH["/casting"]}
        actions={
          <MetricRow>
            <MetricCard label="Total pool" value={ranked.length} />
            <MetricCard label="Locked" value={locked} tone={locked ? "ok" : "plain"} />
            <MetricCard label="Screening" value={screening} tone={screening ? "warn" : "plain"} />
          </MetricRow>
        }
      />

      {statusError && (
        <div className="banner" data-tone="bad" role="alert">
          <Icon name="error" />
          <span>{statusError}</span>
        </div>
      )}

      <Panel className="panel--flex panel--clip">
        <div className="panel-head" style={{ flexWrap: "wrap" }}>
          <div className="search-wrap panel-search">
            <Icon name="search" />
            <input
              className="input"
              type="search"
              placeholder="Search candidates or roles…"
              value={query}
              aria-label="Search candidates"
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="row row--tight">
            <div className="select-wrap">
              <select
                className="select"
                value={statusFilter}
                aria-label="Filter by status"
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="ALL">All statuses</option>
                {statuses.map((s) => (
                  <option key={s} value={s}>
                    {statusLabel(s)}
                  </option>
                ))}
              </select>
              <Icon name="filter_list" />
            </div>
            <button type="button" className="btn btn--tonal" onClick={exportCsv} disabled={!visible.length}>
              <Icon name="download" />
              Export
            </button>
          </div>
        </div>

        {ranked.length === 0 ? (
          <EmptyState
            icon={running ? "progress_activity" : "groups"}
            title={running ? "Agents are sourcing candidates…" : "No candidates yet"}
          >
            {running
              ? "The pre-casting agents are ingesting the talent pool."
              : "Run the pipeline to let the pre-casting and audition agents build the leaderboard."}
          </EmptyState>
        ) : (
          <>
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th className="center" style={{ width: 64 }}>
                      Rnk
                    </th>
                    <th style={{ minWidth: 230 }}>Candidate</th>
                    <th>
                      <span className="row row--tight" style={{ gap: 6 }}>
                        Status
                        {canEdit && <Icon name="edit" size={13} title="Click a status to change it" />}
                      </span>
                    </th>
                    <th style={{ width: 130 }}>Audition</th>
                    <th style={{ width: 130 }}>Hype</th>
                    <th style={{ width: 130 }}>PR</th>
                    <th style={{ width: 130 }}>Budget fit</th>
                    <th className="num" style={{ width: 120 }}>
                      Composite
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((c, i) => {
                    const out = c.status === "DISQUALIFIED";
                    return (
                      <tr key={c.id} className={cn(out && "dimmed")}>
                        <td className={cn("center", i === 0 && !out && "text-primary")}>
                          #{String(i + 1).padStart(2, "0")}
                        </td>
                        <td>
                          <div className="avatar-cell">
                            <span className="avatar-round" aria-hidden="true">
                              {initials(c.name)}
                            </span>
                            <div>
                              <div className="name">{c.name}</div>
                              <div className="sub">
                                {c.role_id || "unassigned role"}
                                {c.metadata?.agency ? ` • ${c.metadata.agency}` : ""}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td>
                          <StatusBadgeSelect
                            status={c.status}
                            options={CASTING_STATUSES}
                            needsReason={NEEDS_REASON}
                            disabled={!canEdit}
                            busy={savingId === c.id}
                            onChange={(next, reason) => changeStatus(c, next, reason)}
                          />
                        </td>
                        <td>
                          <ScoreCell score={c.scores.audition} tone="primary" dim={out} />
                        </td>
                        <td>
                          <ScoreCell score={c.scores.hype} tone="secondary" dim={out} />
                        </td>
                        <td>
                          <ScoreCell score={c.scores.pr} tone="secondary" dim={out} />
                        </td>
                        <td>
                          <ScoreCell score={c.scores.budget} tone="primary" dim={out} />
                        </td>
                        <td className="num">
                          <strong
                            className={cn(i === 0 && !out ? "text-primary" : undefined)}
                            style={{ fontSize: 16 }}
                          >
                            {c.scores.composite?.toFixed?.(1) ?? c.scores.composite ?? "—"}
                          </strong>
                        </td>
                      </tr>
                    );
                  })}
                  {visible.length === 0 && (
                    <tr>
                      <td colSpan={8}>
                        <EmptyState icon="search_off" title="No candidates match">
                          Clear the search or status filter to see the full pool.
                        </EmptyState>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <PanelFoot>
              <span>
                Showing {visible.length} of {ranked.length} candidates
              </span>
              <span>
                Casting status: <span className="text-primary">{statusLabel(state.casting_status)}</span>
                {canEdit && <span className="muted"> · click any status to change it</span>}
              </span>
            </PanelFoot>
          </>
        )}
      </Panel>

      <Panel className="panel--pad">
        <h3 className="panel-title mono-label" style={{ marginBottom: 12 }}>
          <Icon name="gpp_maybe" />
          Risk router — disqualified
        </h3>
        {disqualified.length === 0 ? (
          <p className="muted body-sm">
            {ranked.length ? "No candidate has been disqualified by the risk router." : "Nothing screened yet."}
          </p>
        ) : (
          disqualified.map((c) => (
            <div className="queue-item" key={c.id}>
              <Icon name="block" style={{ color: "var(--status-error)" }} />
              <span>
                <strong>{c.name}</strong> — <span className="muted">{c.disqualify_reason || "no reason recorded"}</span>
              </span>
            </div>
          ))
        )}
      </Panel>
    </>
  );
}
