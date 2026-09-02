import { useMemo, useState } from "react";
import Panel, { PanelFoot, PanelHead } from "../../shared/Panel.jsx";
import PageHeader from "../../shared/PageHeader.jsx";
import MetricCard, { MetricRow } from "../../shared/MetricCard.jsx";
import Meter from "../../shared/Meter.jsx";
import { ArcGauge } from "../../shared/Gauge.jsx";
import StatusBadge from "../../shared/StatusBadge.jsx";
import EmptyState from "../../shared/EmptyState.jsx";
import Icon from "../../shared/Icon.jsx";
import DirectorControls from "./DirectorControls.jsx";
import { api } from "../../lib/api.js";
import { useProject } from "../../shared/ProjectContext.jsx";
import { clampPercent, cn, money, statusLabel, statusTone } from "../../lib/utils.js";
import { STAGE_BY_PATH } from "../../shared/navigation.js";

// ---------------------------------------------------------------------------
// The only placeholder in this file. The backend tracks a single total budget,
// not per-department allocations, so the variance panel needs a planned split
// to compare actuals against. Replace this map with real planned figures the
// moment /api/production exposes them — nothing else here is mocked.
const DEPARTMENT_PLAN_SHARE = {
  Cast: 0.3,
  Crew: 0.22,
  Equipment: 0.18,
  Location: 0.15,
  Makeup: 0.05,
  Other: 0.1,
};
// ---------------------------------------------------------------------------

const EXPENSE_CATEGORIES = ["Equipment", "Cast", "Crew", "Location", "Makeup", "Other"];

// Local-calendar date key. Deliberately not toISOString(), which shifts the day
// across the UTC boundary for anyone east or west of Greenwich.
function ymd(date) {
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${m}-${d}`;
}

const TODAY = ymd(new Date());

// Phase III & IV — schedule intelligence, stripboard, compliance and the cost
// ledger. Layout follows the Stitch "Production Intelligence" bento.
export default function ProdView() {
  const { state, setState, running } = useProject();

  const schedule = state?.schedule || { stripboard: [], conflicts: [] };
  const budgetState = state?.budget_state || {};
  const complianceState = state?.compliance_state || {};
  const stripboard = schedule.stripboard || [];

  const dates = useMemo(() => [...new Set(stripboard.map((e) => e.date))].sort(), [stripboard]);

  const [calendarMode, setCalendarMode] = useState("week");
  const [calendarOffset, setCalendarOffset] = useState(0);
  const [selectedMonth, setSelectedMonth] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [expense, setExpense] = useState({ category: "Equipment", description: "", amount: "" });
  const [expenseError, setExpenseError] = useState("");
  const [note, setNote] = useState({ date: "", missed_scene_ids: [], reshoot_date: "", note: "" });
  const [noteError, setNoteError] = useState("");
  const [noteSaved, setNoteSaved] = useState(false);

  const calendarYear = Number(dates[0]?.slice(0, 4)) || new Date().getFullYear();
  const activeMonth = selectedMonth ?? (Number(dates[0]?.slice(5, 7)) || new Date().getMonth() + 1) - 1;
  const noteDate = note.date || dates[0] || "";

  const visibleDates = useMemo(() => {
    if (calendarMode === "year") return [];
    const windowSize =
      calendarMode === "month" ? new Date(calendarYear, activeMonth + 1, 0).getDate() : 7;
    const start =
      calendarMode === "month"
        ? new Date(calendarYear, activeMonth, 1)
        : new Date(`${dates[0] || TODAY}T00:00:00`);
    if (calendarMode === "week") start.setDate(start.getDate() + calendarOffset * 7);
    return Array.from({ length: windowSize }, (_, i) => {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      return ymd(d);
    });
  }, [calendarMode, calendarOffset, calendarYear, activeMonth, dates]);

  // Every day of the shooting year — powers the year grid and the reshoot picker.
  const calendarDates = useMemo(
    () =>
      Array.from({ length: 365 }, (_, i) => {
        const d = new Date(calendarYear, 0, 1);
        d.setDate(i + 1);
        return ymd(d);
      }),
    [calendarYear]
  );

  // Actual spend per department against the planned split above.
  const variance = useMemo(() => {
    const expenses = budgetState.expenses || [];
    const total = Number(budgetState.total_budget) || 0;
    const actual = expenses.reduce((acc, e) => {
      acc[e.category] = (acc[e.category] || 0) + Number(e.amount || 0);
      return acc;
    }, {});
    return Object.keys(actual)
      .map((category) => {
        const spent = actual[category];
        const planned = total * (DEPARTMENT_PLAN_SHARE[category] ?? 0.1);
        return { category, spent, planned, over: planned > 0 && spent > planned };
      })
      .sort((a, b) => b.spent - a.spent);
  }, [budgetState]);

  // Stitch reads this gauge as "% of planned daily average", so the daily burn
  // is measured against the ledger budget spread over the scheduled shoot days
  // rather than against the whole-production cap.
  const cap = budgetState.cap || 4000;
  const plannedDaily = (budgetState.total_budget || cap) / Math.max(1, dates.length);
  const burnPercent = clampPercent(plannedDaily > 0 ? (budgetState.daily_burn / plannedDaily) * 100 : 0);
  const burnTone = burnPercent >= 90 ? "bad" : burnPercent >= 70 ? "warn" : "ok";
  const territories = Object.entries(complianceState);
  const scenesOnNoteDate = stripboard.filter((e) => e.date === noteDate);

  async function submitExpense(event) {
    event.preventDefault();
    setExpenseError("");
    try {
      const budget = await api.addExpense(state.project_id, { ...expense, amount: Number(expense.amount) });
      setState({ ...state, budget_state: budget });
      setExpense({ category: expense.category, description: "", amount: "" });
    } catch (e) {
      setExpenseError(String(e.message || e));
    }
  }

  async function submitNote(event) {
    event.preventDefault();
    setNoteError("");
    setNoteSaved(false);
    try {
      const updated = await api.updateShootDay(state.project_id, { ...note, date: noteDate });
      setState(updated);
      setNote({ date: noteDate, missed_scene_ids: [], reshoot_date: "", note: "" });
      setNoteSaved(true);
    } catch (e) {
      setNoteError(String(e.message || e));
    }
  }

  if (!state) {
    return (
      <>
        <PageHeader title="Production Intelligence" sub="Schedule, compliance and cost intelligence for the active shoot." meta={STAGE_BY_PATH["/schedule"]} />
        <Panel>
          <EmptyState icon={running ? "progress_activity" : "event_note"} title={running ? "Agents are building the schedule…" : "No project state yet"}>
            Run the pipeline to generate the stripboard, compliance matrix and cost ledger.
          </EmptyState>
        </Panel>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Production Intelligence"
        meta={
          <>
            Project: <span className="text-primary">{state.project_id}</span> | Casting:{" "}
            <span className="text-ok">{statusLabel(state.casting_status)}</span>
          </>
        }
        actions={
          <>
            <button type="button" className="btn btn--ghost" onClick={() => window.print()}>
              <Icon name="print" />
              Export report
            </button>
            <button type="button" className="btn btn--primary" onClick={() => setSettingsOpen((o) => !o)}>
              <Icon name="tune" />
              {settingsOpen ? "Close controls" : "Agent override"}
            </button>
          </>
        }
      />

      <MetricRow>
        <MetricCard label="Daily burn" value={money(budgetState.daily_burn)} tone={burnTone} />
        <MetricCard label="Scenes scheduled" value={stripboard.length} />
        <MetricCard label="Conflicts resolved" value={(schedule.conflicts || []).length} />
        <MetricCard label="Shoot days" value={dates.length} />
      </MetricRow>

      {settingsOpen && (
        <Panel className="panel--pad">
          <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
            <Icon name="tune" />
            Director controls
          </h3>
          <DirectorControls onSaved={() => setSettingsOpen(false)} />
        </Panel>
      )}

      <div className="grid">
        {/* Burn rate gauge */}
        <Panel sunken className="span-4 panel--pad panel--flex relative" style={{ overflow: "hidden" }}>
          <div className="tint-wash" />
          <h3 className="panel-title mono-label" style={{ marginBottom: 24, position: "relative" }}>
            Burn rate meter
          </h3>
          <ArcGauge value={burnPercent} tone={burnTone} label="Burn rate" caption="of planned daily average" />
          <p className="mono-data muted" style={{ marginTop: 8, textAlign: "center" }}>
            {money(budgetState.daily_burn)} / {money(plannedDaily)} per shoot day
          </p>
          {(budgetState.alerts || []).length > 0 && (
            <div className="banner" data-tone="bad" style={{ marginTop: 16 }}>
              <Icon name="local_fire_department" />
              <span>{budgetState.alerts.join(" ")}</span>
            </div>
          )}
        </Panel>

        {/* Budget variance */}
        <Panel sunken className="span-8 panel--pad">
          <div className="between" style={{ marginBottom: 24 }}>
            <h3 className="panel-title mono-label">Budget variance</h3>
            <div className="legend">
              <span>
                <i style={{ background: "var(--primary-container)" }} /> Actual
              </span>
              <span>
                <i style={{ background: "var(--surface-variant)" }} /> Planned
              </span>
            </div>
          </div>
          {variance.length === 0 ? (
            <EmptyState icon="payments" title="No spend recorded">
              Log an expense below and the department variance appears here.
            </EmptyState>
          ) : (
            variance.map((row) => (
              <div className="variance-row" key={row.category}>
                <div className="variance-head">
                  <span>{row.category}</span>
                  <span className={cn("nums", row.over ? "text-bad" : "muted")}>
                    {money(row.spent)} / {money(row.planned)}
                  </span>
                </div>
                <Meter
                  value={row.planned > 0 ? (row.spent / row.planned) * 100 : 100}
                  tone={row.over ? "bad" : undefined}
                />
              </div>
            ))
          )}
        </Panel>

        {/* Stripboard */}
        <Panel sunken className="span-12 panel--clip">
          <PanelHead title="Live stripboard">
            <div className="row row--tight">
              <span className="tag-chip">INT</span>
              <span className="tag-chip on">EXT</span>
              {calendarMode === "week" && (
                <>
                  <button
                    type="button"
                    className="btn btn--icon"
                    onClick={() => setCalendarOffset((o) => o - 1)}
                    aria-label="Previous week"
                  >
                    <Icon name="chevron_left" size={20} />
                  </button>
                  <button
                    type="button"
                    className="btn btn--icon"
                    onClick={() => setCalendarOffset((o) => o + 1)}
                    aria-label="Next week"
                  >
                    <Icon name="chevron_right" size={20} />
                  </button>
                </>
              )}
              <div className="pill-toggle">
                {["week", "month", "year"].map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={cn(calendarMode === mode && "active")}
                    onClick={() => {
                      setCalendarMode(mode);
                      setCalendarOffset(0);
                    }}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
          </PanelHead>

          {stripboard.length === 0 ? (
            <EmptyState icon="calendar_month" title="Stripboard empty">
              The schedule agent has not laid out any scenes yet.
            </EmptyState>
          ) : calendarMode === "year" ? (
            <div className="panel--pad">
              <div className="month-grid">
                {Array.from({ length: 12 }, (_, month) => {
                  const shootDays = calendarDates.filter(
                    (date) => Number(date.slice(5, 7)) - 1 === month && stripboard.some((e) => e.date === date)
                  );
                  return (
                    <button
                      type="button"
                      key={month}
                      className={cn("month-tile", month === activeMonth && "selected")}
                      onClick={() => {
                        setSelectedMonth(month);
                        setCalendarMode("month");
                      }}
                    >
                      <strong>{new Date(calendarYear, month, 1).toLocaleString("en", { month: "long" })}</strong>
                      <small>{shootDays.length} shoot days</small>
                      <div className="month-dots">
                        {shootDays.map((date) => (
                          <i key={date} />
                        ))}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <>
              <div className="panel--pad" style={{ paddingBottom: 0 }}>
                <span className="mono-data muted">
                  {calendarMode.toUpperCase()} VIEW · {visibleDates[0]} → {visibleDates[visibleDates.length - 1]}
                </span>
              </div>
              <div className="stripboard">
                <div className="strip-grid" style={{ "--days": visibleDates.length }}>
                  <div className="strip-row strip-row--head">
                    <div>Scene / requirements</div>
                    {visibleDates.map((date) => (
                      <div key={date} className={cn(date === TODAY && "today")}>
                        {date.slice(5)}
                        {date === TODAY ? " ·" : ""}
                      </div>
                    ))}
                  </div>
                  <div className="strip-body">
                    {stripboard.map((entry) => (
                      <div className="strip-row" key={entry.scene_id}>
                        <div className="strip-scene">
                          <div className="id">{entry.scene_id}</div>
                          <div className="meta">
                            {entry.int_ext} · {entry.location_type} · {entry.estimated_time_hours}h
                            {entry.characters_needed?.length ? ` · cast ${entry.characters_needed.length}` : ""}
                          </div>
                          {entry.status === "PARTIAL" && (
                            <div className="warn">
                              <Icon name="warning" />
                              Carried over
                            </div>
                          )}
                        </div>
                        {visibleDates.map((date) => (
                          <div className="strip-cell" key={date}>
                            {date === entry.date && (
                              <span
                                className="strip-bar"
                                data-kind={
                                  entry.status === "PARTIAL"
                                    ? "TBD"
                                    : /EXT/i.test(entry.int_ext || "")
                                    ? "EXT"
                                    : "INT"
                                }
                                title={`${entry.venue} — ${entry.int_ext} ${entry.location_type}`}
                              >
                                {/* clamped to two lines so a long venue name can
                                    never inflate the bar or spill out of the cell;
                                    the full name stays available on hover */}
                                <span className="strip-bar-text">{entry.venue}</span>
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
              <PanelFoot>
                <span>
                  {stripboard.length} scenes · {dates.length} shoot days
                </span>
                <span>{(schedule.conflicts || []).length} conflicts resolved by the schedule agent</span>
              </PanelFoot>
            </>
          )}
        </Panel>

        {/* Compliance matrix */}
        <Panel sunken className="span-12 panel--pad">
          <div className="between" style={{ marginBottom: 16 }}>
            <h3 className="panel-title mono-label">Location compliance matrix</h3>
            <span className="mono-data muted">Live clearance</span>
          </div>
          {territories.length === 0 ? (
            <EmptyState icon="public" title="No territories evaluated">
              The compliance sweep has not run yet.
            </EmptyState>
          ) : (
            <div className="matrix">
              {territories.map(([territory, status]) => {
                const tone = statusTone(status);
                return (
                  <div className="matrix-card" key={territory} data-tone={tone}>
                    <div className="tint" />
                    <div className="head">
                      <span>{territory}</span>
                      <span className="lamp" data-tone={tone} />
                    </div>
                    <dl>
                      <div>
                        <span>Clearance:</span>
                        <span className={tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : undefined}>
                          {statusLabel(status)}
                        </span>
                      </div>
                      <div>
                        <span>Territory:</span>
                        <span>{territory}</span>
                      </div>
                    </dl>
                    <StatusBadge status={status} />
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        {/* Cost ledger */}
        <Panel className="span-12 panel--clip">
          <PanelHead title="Cost ledger" icon="receipt_long">
            <span className={cn("mono-data", budgetState.remaining < 0 ? "text-bad" : "text-ok")}>
              {money(budgetState.remaining)} left
            </span>
          </PanelHead>
          <div className="panel--pad stack">
            <div className="stat-row">
              <MetricCard label="Total budget" value={money(budgetState.total_budget)} tone="plain" />
              <MetricCard label="Spent" value={money(budgetState.spent)} tone="warn" />
              <MetricCard
                label="Remaining"
                value={money(budgetState.remaining)}
                tone={budgetState.remaining < 0 ? "bad" : "ok"}
              />
            </div>
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th>Description</th>
                    <th className="num">Amount</th>
                  </tr>
                </thead>
                <tbody>
                  {(budgetState.expenses || []).map((item, index) => (
                    <tr key={`${item.description}-${index}`}>
                      <td>{item.category}</td>
                      <td>{item.description}</td>
                      <td className="num">{money(item.amount)}</td>
                    </tr>
                  ))}
                  {(budgetState.expenses || []).length === 0 && (
                    <tr>
                      <td colSpan={3}>
                        <EmptyState icon="receipt" title="No expenses logged" />
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {expenseError && (
              <div className="banner" data-tone="bad" role="alert">
                <Icon name="error" />
                <span>{expenseError}</span>
              </div>
            )}
            <form className="form-grid" onSubmit={submitExpense}>
              <label className="field">
                <span className="mono-label">Category</span>
                <div className="select-wrap">
                  <select
                    className="select"
                    value={expense.category}
                    onChange={(e) => setExpense({ ...expense, category: e.target.value })}
                  >
                    {EXPENSE_CATEGORIES.map((c) => (
                      <option key={c}>{c}</option>
                    ))}
                  </select>
                  <Icon name="arrow_drop_down" />
                </div>
              </label>
              <label className="field" style={{ gridColumn: "span 2" }}>
                <span className="mono-label">Description</span>
                <input
                  className="input"
                  required
                  placeholder="Expense description"
                  value={expense.description}
                  onChange={(e) => setExpense({ ...expense, description: e.target.value })}
                />
              </label>
              <label className="field">
                <span className="mono-label">Amount (USD)</span>
                <input
                  className="input"
                  required
                  type="number"
                  min="1"
                  placeholder="0"
                  value={expense.amount}
                  onChange={(e) => setExpense({ ...expense, amount: e.target.value })}
                />
              </label>
              <button type="submit" className="btn btn--primary">
                <Icon name="add" />
                Add expense
              </button>
            </form>
          </div>
        </Panel>

        {/* Shoot-day feedback */}
        <Panel className="span-12 panel--pad">
          <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
            <Icon name="assignment_turned_in" />
            Shoot-day feedback
          </h3>
          {dates.length === 0 ? (
            <EmptyState icon="event_busy" title="No shoot days scheduled" />
          ) : (
            <form className="stack" onSubmit={submitNote}>
              <div className="form-grid">
                <label className="field">
                  <span className="mono-label">Date</span>
                  <div className="select-wrap">
                    <select
                      className="select"
                      value={noteDate}
                      onChange={(e) => setNote({ ...note, date: e.target.value, missed_scene_ids: [] })}
                    >
                      {dates.map((date) => (
                        <option key={date}>{date}</option>
                      ))}
                    </select>
                    <Icon name="arrow_drop_down" />
                  </div>
                </label>
                <label className="field">
                  <span className="mono-label">Move missed scenes to</span>
                  <div className="select-wrap">
                    <select
                      className="select"
                      value={note.reshoot_date}
                      onChange={(e) => setNote({ ...note, reshoot_date: e.target.value })}
                    >
                      <option value="">Select a reshoot date</option>
                      {calendarDates
                        .filter((date) => date > noteDate)
                        .map((date) => (
                          <option key={date}>{date}</option>
                        ))}
                    </select>
                    <Icon name="arrow_drop_down" />
                  </div>
                </label>
                <fieldset className="check-set" style={{ gridColumn: "span 2" }}>
                  <legend>Scenes not completed</legend>
                  <div className="check-row">
                    {scenesOnNoteDate.length === 0 && <span className="muted body-sm">No scenes on this date.</span>}
                    {scenesOnNoteDate.map((entry) => (
                      <label className="check-label" key={entry.scene_id}>
                        <input
                          type="checkbox"
                          checked={note.missed_scene_ids.includes(entry.scene_id)}
                          onChange={(e) =>
                            setNote({
                              ...note,
                              missed_scene_ids: e.target.checked
                                ? [...note.missed_scene_ids, entry.scene_id]
                                : note.missed_scene_ids.filter((id) => id !== entry.scene_id),
                            })
                          }
                        />
                        {entry.scene_id}
                      </label>
                    ))}
                  </div>
                </fieldset>
              </div>
              <label className="field">
                <span className="mono-label">Director note</span>
                <textarea
                  className="textarea"
                  placeholder="What happened on set?"
                  value={note.note}
                  onChange={(e) => setNote({ ...note, note: e.target.value })}
                />
              </label>
              {noteError && (
                <div className="banner" data-tone="bad" role="alert">
                  <Icon name="error" />
                  <span>{noteError}</span>
                </div>
              )}
              {noteSaved && (
                <div className="banner" data-tone="warn" role="status">
                  <Icon name="check_circle" />
                  <span>Schedule updated from the day's report.</span>
                </div>
              )}
              <div className="form-actions">
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={note.missed_scene_ids.length > 0 && !note.reshoot_date}
                >
                  <Icon name="update" />
                  Update schedule
                </button>
              </div>
            </form>
          )}
        </Panel>
      </div>
    </>
  );
}
