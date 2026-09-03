import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
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
  const { state, running, canEdit, projectId, applyCandidateUpdate, locality, directorNotes, runCasting } = useProject();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [savingId, setSavingId] = useState(null);
  const [statusError, setStatusError] = useState("");
  const [showScoutModal, setShowScoutModal] = useState(false);

  const activeLocality = state?.locality || state?.script_context?.locality || locality || "Atlanta, GA";
  const activeNotes = state?.director_notes || state?.script_context?.director_notes || directorNotes || "";
  const [scoutLocality, setScoutLocality] = useState(activeLocality);
  const [scoutNotes, setScoutNotes] = useState(activeNotes);
  const [scouting, setScouting] = useState(false);

  async function triggerScout(e) {
    if (e) e.preventDefault();
    setScouting(true);
    setStatusError("");
    try {
      await runCasting(scoutLocality, scoutNotes);
      setShowScoutModal(false);
    } catch (err) {
      setStatusError(`Google Cloud Talent Scout Agent error: ${err.message || err}`);
    } finally {
      setScouting(false);
    }
  }

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
        sub={`Real-time candidate evaluation for ${state?.project_id || "this project"}. Sourcing and ranking powered by Google Cloud Autonomous Talent Scout Agent.`}
        meta={
          <div className="stack stack--xs">
            {STAGE_BY_PATH["/casting"]}
            <div className="row row--tight" style={{ gap: 8, marginTop: 4, flexWrap: "wrap" }}>
              <span className="badge" title="Target Locality for Local Hire Actors" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Icon name="location_on" size={13} />
                <span>Locality: <strong>{activeLocality}</strong></span>
              </span>
              <span className="badge" title="Maximum per-role budget allocation" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Icon name="attach_money" size={13} />
                <span>Role Cap: <strong>${Math.round((state?.budget_state?.cap || 250000) * 0.1).toLocaleString()}</strong></span>
              </span>
              {activeNotes && (
                <span className="badge" title={`Director Notes: ${activeNotes}`} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                  <Icon name="movie" size={13} />
                  <span>Notes: <strong>{activeNotes.length > 30 ? activeNotes.slice(0, 30) + "…" : activeNotes}</strong></span>
                </span>
              )}
            </div>
          </div>
        }
        actions={
          <>
            <MetricRow>
              <MetricCard label="Total pool" value={ranked.length} />
              <MetricCard label="Locked" value={locked} tone={locked ? "ok" : "plain"} />
              <MetricCard label="Screening" value={screening} tone={screening ? "warn" : "plain"} />
            </MetricRow>
            <div className="row row--tight" style={{ gap: 8 }}>
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => {
                  setScoutLocality(activeLocality);
                  setScoutNotes(activeNotes);
                  setShowScoutModal((s) => !s);
                }}
                disabled={running || scouting || !canEdit}
                title="Crawl and scout local actors using Google Cloud Agent"
              >
                <Icon name={scouting ? "progress_activity" : "radar"} className={scouting ? "spin" : undefined} />
                <span>{scouting ? "Scouting..." : "Scout Local Talent"}</span>
              </button>
              <Link to="/advisors?advisor=casting" className="btn btn--ghost" title="Ask the Casting Advisor for a recommendation">
                <Icon name="auto_awesome" />
                Casting Advisor
              </Link>
            </div>
          </>
        }
      />

      {showScoutModal && (
        <Panel className="panel--pad stack" style={{ border: "1px solid var(--primary)", background: "var(--surface-elevated, #161a22)", borderRadius: 8 }}>
          <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
            <h3 className="panel-title mono-label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Icon name="travel_explore" />
              Google Cloud Talent Scout Agent — Crawler Configuration
            </h3>
            <button type="button" className="btn btn--icon btn--ghost" onClick={() => setShowScoutModal(false)}>
              <Icon name="close" size={16} />
            </button>
          </div>
          <p className="body-sm muted">
            Directs the Google Cloud casting agent to crawl local agency rosters, actor databases, and casting calls in your locality, strictly vetted to fit within your per-role budget cap and director notes.
          </p>
          <div className="grid grid--2" style={{ gap: 16 }}>
            <div>
              <label className="mono-label muted" style={{ display: "block", marginBottom: 6 }}>
                Filming Locality / Talent Market
              </label>
              <input
                className="input"
                value={scoutLocality}
                onChange={(e) => setScoutLocality(e.target.value)}
                placeholder="e.g. Atlanta, GA or London, UK or New York, NY"
              />
            </div>
            <div>
              <label className="mono-label muted" style={{ display: "block", marginBottom: 6 }}>
                Per-Role Budget Cap (USD)
              </label>
              <input
                className="input"
                disabled
                value={`$${Math.round((state?.budget_state?.cap || 250000) * 0.1).toLocaleString()} USD (10% of total budget)`}
              />
            </div>
          </div>
          <div>
            <label className="mono-label muted" style={{ display: "block", marginBottom: 6 }}>
              Director's Casting Notes & Specific Requirements
            </label>
            <textarea
              className="textarea"
              rows={3}
              value={scoutNotes}
              onChange={(e) => setScoutNotes(e.target.value)}
              placeholder="e.g. Gritty realism, martial arts stunt experience, local theater roots, bilingual..."
            />
          </div>
          <div className="row" style={{ justifyContent: "flex-end", gap: 8 }}>
            <button type="button" className="btn btn--ghost" onClick={() => setShowScoutModal(false)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn btn--primary"
              onClick={triggerScout}
              disabled={running || scouting || !canEdit}
            >
              <Icon name={scouting ? "progress_activity" : "search"} className={scouting ? "spin" : undefined} />
              <span>{scouting ? "Google Cloud Agent Crawling..." : "Crawl & Scout Candidates"}</span>
            </button>
          </div>
        </Panel>
      )}

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
            icon={running || scouting ? "progress_activity" : "groups"}
            title={running || scouting ? "Google Cloud Agent is crawling talent..." : "No candidates yet"}
          >
            {running || scouting
              ? `The Google Cloud Agent is crawling talent agencies and local rosters in ${activeLocality} within your budget cap.`
              : `Click "Scout Local Talent" or run the pipeline to crawl actors in ${activeLocality} matching your director notes.`}
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
                                {c.metadata?.locality ? ` • 📍 ${c.metadata.locality}` : ""}
                                {c.metadata?.agency ? ` • ${c.metadata.agency}` : ""}
                                {c.metadata?.quote_usd ? ` • Quote: $${Number(c.metadata.quote_usd).toLocaleString()}` : ""}
                              </div>
                              <div className="row row--tight" style={{ gap: 6, marginTop: 3, flexWrap: "wrap" }}>
                                {c.metadata?.is_live_scouted ? (
                                  <span className="badge" style={{ fontSize: 10, padding: "1px 6px", color: "var(--status-ok, #3fb950)", borderColor: "rgba(63, 185, 80, 0.4)" }} title="Live scouted via Google Cloud Gemini + Google Search Grounding">
                                    🟢 Live Google Search
                                  </span>
                                ) : (
                                  <span className="badge" style={{ fontSize: 10, padding: "1px 6px", color: "var(--text-muted, #8b949e)" }} title="Generated via locality-based synthesis fallback (no GEMINI_API_KEY set)">
                                    ⚪ Offline Locality Synthesis
                                  </span>
                                )}
                                {c.metadata?.director_match && (
                                  <span className="muted body-sm" style={{ fontSize: 11 }}>
                                    <span style={{ color: "var(--primary)", fontWeight: 500 }}>🎯 Match:</span>{" "}
                                    {c.metadata.director_match}
                                  </span>
                                )}
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
