import { useState } from "react";
import { STATUS_COLORS } from "../../lib/utils.js";
import { api } from "../../lib/api.js";

// Phase III & IV dashboard: stripboard, burn rate, territory compliance.
export default function ProdView({ state, onStateChange }) {
  if (!state) return <div className="empty">No project state yet.</div>;
  const { schedule, budget_state, compliance_state } = state;
  const dates = [...new Set(schedule.stripboard.map((entry) => entry.date))].sort();
  const cap = budget_state.cap || 4000;
  const burnPercent = Math.min((budget_state.daily_burn / cap) * 100, 100);
  const territoryEntries = Object.entries(compliance_state);
  const statusIcon = { CLEARED: "OK", AWAITING_QC: "QC", BLOCKED: "!" };
  const [calendarMode, setCalendarMode] = useState("week");
  const [calendarOffset, setCalendarOffset] = useState(0);
  const [selectedMonth, setSelectedMonth] = useState(Number(dates[0]?.slice(5, 7) || 9) - 1);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [expense, setExpense] = useState({ category: "Equipment", description: "", amount: "" });
  const [note, setNote] = useState({ date: dates[0] || "", missed_scene_ids: [], reshoot_date: "", note: "" });
  const settings = { country: state.schedule.director_constraints?.country || "USA", excluded_states: (state.schedule.director_constraints?.excluded_states || []).join(", "), start_date: state.schedule.shoot_settings?.start_date || "2026-09-01", min_hours_per_day: state.schedule.shoot_settings?.min_hours_per_day || 6, max_hours_per_day: state.schedule.shoot_settings?.max_hours_per_day || 10, total_budget: budget_state.total_budget || 100000 };
  const [formSettings, setFormSettings] = useState(settings);
  const calendarYear = Number(dates[0]?.slice(0, 4) || 2026);
  const windowSize = calendarMode === "month" ? new Date(calendarYear, selectedMonth + 1, 0).getDate() : 7;
  const calendarStart = calendarMode === "month" ? new Date(calendarYear, selectedMonth, 1) : new Date(`${dates[0] || "2026-09-01"}T00:00:00`);
  calendarStart.setDate(calendarStart.getDate() + (calendarMode === "week" ? calendarOffset * 7 : 0));
  const visibleDates = calendarMode === "year" ? [] : Array.from({ length: windowSize }, (_, index) => {
    const current = new Date(calendarStart);
    current.setDate(calendarStart.getDate() + index);
    return current.toISOString().slice(0, 10);
  });
  const calendarDates = Array.from({ length: 365 }, (_, index) => {
    const current = new Date(calendarYear, 0, 1);
    current.setDate(index + 1);
    return current.toISOString().slice(0, 10);
  });
  const saveSettings = async (event) => {
    event.preventDefault();
    const updated = await api.updateProductionSettings(state.project_id, { ...formSettings, excluded_states: formSettings.excluded_states.split(",").map((item) => item.trim()).filter(Boolean), min_hours_per_day: Number(formSettings.min_hours_per_day), max_hours_per_day: Number(formSettings.max_hours_per_day), total_budget: Number(formSettings.total_budget) });
    onStateChange(updated);
    setSettingsOpen(false);
  };
  const submitExpense = async (event) => {
    event.preventDefault();
    const budget = await api.addExpense(state.project_id, { ...expense, amount: Number(expense.amount) });
    onStateChange({ ...state, budget_state: budget });
    setExpense({ category: expense.category, description: "", amount: "" });
  };
  const submitNote = async (event) => {
    event.preventDefault();
    const updated = await api.updateShootDay(state.project_id, note);
    onStateChange(updated);
  };

  return (
    <>
      <div className="card">
        <div className="section-heading">
          <div><div className="eyebrow">Production control</div><h2>Schedule intelligence</h2></div>
        </div>
        <div className="metric-row">
          <div className="metric">
            <div className="value">${Math.round(budget_state.daily_burn).toLocaleString()}</div>
            <div className="label">Daily burn</div>
          </div>
          <div className="metric">
            <div className="value">{schedule.stripboard.length}</div>
            <div className="label">Scenes scheduled</div>
          </div>
          <div className="metric">
            <div className="value">{schedule.conflicts.length}</div>
            <div className="label">Conflicts resolved</div>
          </div>
          <div className="metric">
            <div className="value">{dates.length}</div>
            <div className="label">Shoot days</div>
          </div>
        </div>
        <div className="burn-meter">
          <div className="burn-label"><span>Daily burn against cap</span><strong>${Math.round(budget_state.daily_burn).toLocaleString()} / ${cap.toLocaleString()}</strong></div>
          <div className="meter-track"><div className={burnPercent >= 90 ? "meter-fill danger" : "meter-fill"} style={{ width: `${burnPercent}%` }} /></div>
          {budget_state.alerts.length > 0 && <div className="alert-line">{budget_state.alerts.join(" ")}</div>}
        </div>
        <button className="secondary-button" onClick={() => setSettingsOpen(!settingsOpen)}>{settingsOpen ? "Close director controls" : "Director controls"}</button>
        {settingsOpen && <form className="settings-form" onSubmit={saveSettings}>
          <label>Country<input value={formSettings.country} onChange={(e) => setFormSettings({ ...formSettings, country: e.target.value })} /></label>
          <label>Exclude states<input placeholder="NV, TX" value={formSettings.excluded_states} onChange={(e) => setFormSettings({ ...formSettings, excluded_states: e.target.value })} /></label>
          <label>First shoot day<input type="date" value={formSettings.start_date} onChange={(e) => setFormSettings({ ...formSettings, start_date: e.target.value })} /></label>
          <label>Min hours/day<input type="number" min="1" value={formSettings.min_hours_per_day} onChange={(e) => setFormSettings({ ...formSettings, min_hours_per_day: e.target.value })} /></label>
          <label>Max hours/day<input type="number" min="1" value={formSettings.max_hours_per_day} onChange={(e) => setFormSettings({ ...formSettings, max_hours_per_day: e.target.value })} /></label>
          <label>Total budget<input type="number" min="0" value={formSettings.total_budget} onChange={(e) => setFormSettings({ ...formSettings, total_budget: e.target.value })} /></label>
          <button className="primary" type="submit">Save and reconfigure</button>
        </form>}
      </div>
      <div className="card">
        <div className="section-heading"><div><div className="eyebrow">Unit plan</div><h2>Stripboard</h2></div><div className="calendar-tools"><button onClick={() => setCalendarOffset(calendarOffset - 1)} aria-label="Previous period">←</button><button onClick={() => setCalendarOffset(calendarOffset + 1)} aria-label="Next period">→</button><select value={calendarMode} onChange={(e) => { setCalendarMode(e.target.value); setCalendarOffset(0); }}><option value="week">Week</option><option value="month">Month</option><option value="year">Year</option></select></div></div>
        {calendarMode === "year" ? <div className="year-grid">{Array.from({ length: 12 }, (_, month) => <button className={month === selectedMonth ? "month-tile selected" : "month-tile"} key={month} onClick={() => { setSelectedMonth(month); setCalendarMode("month"); }}><strong>{new Date(calendarYear, month, 1).toLocaleString("en", { month: "long" })}</strong><small>{calendarDates.filter((date) => Number(date.slice(5, 7)) - 1 === month && schedule.stripboard.some((entry) => entry.date === date)).length} shoot days</small><div className="month-dots">{calendarDates.filter((date) => Number(date.slice(5, 7)) - 1 === month && schedule.stripboard.some((entry) => entry.date === date)).map((date) => <i key={date} />)}</div></button>)}</div> : <>
        <div className="calendar-caption">{calendarMode.toUpperCase()} VIEW · {visibleDates[0]} → {visibleDates[visibleDates.length - 1]}</div>
        <div className="gantt" style={{ "--days": visibleDates.length }}>
          <div className="gantt-row gantt-head"><span>Scene / requirements</span>{visibleDates.map((date) => <span key={date}>{date.slice(5)}</span>)}</div>
          {schedule.stripboard.map((entry) => (
            <div className="gantt-row" key={entry.scene_id}>
              <div className="scene-label"><strong>{entry.scene_id}</strong><small>{entry.int_ext} · {entry.location_type} · {entry.estimated_time_hours}h</small></div>
              {visibleDates.map((date) => <div className={date === entry.date ? "gantt-cell active" : "gantt-cell"} key={date}>{date === entry.date && <span>{entry.venue}</span>}</div>)}
            </div>
          ))}
        </div>
        </>}
      </div>
      <div className="card">
        <div className="section-heading"><div><div className="eyebrow">Rights + localization</div><h2>Territory readiness</h2></div><span className="muted-note">Live clearance matrix</span></div>
        {territoryEntries.length === 0 ? <span className="empty">Phase IV not run yet.</span> : <div className="territory-map" aria-label="Territory compliance map">
          {territoryEntries.map(([territory, status]) => <div className="territory" key={territory} data-status={status}>
            <span className="territory-code">{territory}</span><span className="territory-status" style={{ color: STATUS_COLORS[status] }}>{statusIcon[status] || "--"}</span><small>{status.replace("_", " ")}</small>
          </div>)}
        </div>}
      </div>
      <div className="card budget-card">
        <div className="section-heading"><div><div className="eyebrow">Cost ledger</div><h2>Budget dashboard</h2></div><strong className={budget_state.remaining < 0 ? "bad-text" : "good-text"}>${Math.round(budget_state.remaining || 0).toLocaleString()} left</strong></div>
        <div className="budget-summary"><span>Budget <strong>${Math.round(budget_state.total_budget || 0).toLocaleString()}</strong></span><span>Spent <strong>${Math.round(budget_state.spent || 0).toLocaleString()}</strong></span></div>
        <table><thead><tr><th>Category</th><th>Description</th><th>Amount</th></tr></thead><tbody>{(budget_state.expenses || []).map((item, index) => <tr key={`${item.description}-${index}`}><td>{item.category}</td><td>{item.description}</td><td>${Number(item.amount).toLocaleString()}</td></tr>)}</tbody></table>
        <form className="expense-form" onSubmit={submitExpense}><select value={expense.category} onChange={(e) => setExpense({ ...expense, category: e.target.value })}><option>Equipment</option><option>Cast</option><option>Crew</option><option>Location</option><option>Makeup</option><option>Other</option></select><input required placeholder="Expense description" value={expense.description} onChange={(e) => setExpense({ ...expense, description: e.target.value })} /><input required type="number" min="1" placeholder="$" value={expense.amount} onChange={(e) => setExpense({ ...expense, amount: e.target.value })} /><button className="primary" type="submit">Add expense</button></form>
      </div>
      <div className="card">
        <div className="section-heading"><div><div className="eyebrow">Daily report</div><h2>Shoot-day feedback</h2></div></div>
        <form className="note-form" onSubmit={submitNote}><label>Date<select value={note.date} onChange={(e) => setNote({ ...note, date: e.target.value, missed_scene_ids: [] })}>{dates.map((date) => <option key={date}>{date}</option>)}</select></label><fieldset><legend>Scenes not completed</legend>{schedule.stripboard.filter((entry) => entry.date === note.date).map((entry) => <label className="check-label" key={entry.scene_id}><input type="checkbox" checked={note.missed_scene_ids.includes(entry.scene_id)} onChange={(e) => setNote({ ...note, missed_scene_ids: e.target.checked ? [...note.missed_scene_ids, entry.scene_id] : note.missed_scene_ids.filter((id) => id !== entry.scene_id) })} />{entry.scene_id}</label>)}</fieldset><label>Move missed scenes to<select value={note.reshoot_date} onChange={(e) => setNote({ ...note, reshoot_date: e.target.value })}><option value="">Select a reshoot date</option>{calendarDates.filter((date) => date > note.date).map((date) => <option key={date}>{date}</option>)}</select></label><label>Director note<textarea placeholder="What happened on set?" value={note.note} onChange={(e) => setNote({ ...note, note: e.target.value })} /></label><button className="primary" type="submit" disabled={note.missed_scene_ids.length > 0 && !note.reshoot_date}>Update schedule</button></form>
      </div>
    </>
  );
}
