import { useState } from "react";
import { api } from "../../lib/api.js";
import { useProject } from "../../shared/ProjectContext.jsx";
import Icon from "../../shared/Icon.jsx";

// Director constraints that reconfigure the schedule agent
// (PUT /api/production/settings/{project_id}). Extracted from ProdView so the
// Settings route can host the same form without duplicating the logic.
export default function DirectorControls({ onSaved }) {
  const { state, setState } = useProject();
  const budget = state?.budget_state || {};
  const schedule = state?.schedule || {};

  const [form, setForm] = useState({
    country: schedule.director_constraints?.country || "USA",
    excluded_states: (schedule.director_constraints?.excluded_states || []).join(", "),
    start_date: schedule.shoot_settings?.start_date || "2026-09-01",
    min_hours_per_day: schedule.shoot_settings?.min_hours_per_day || 6,
    max_hours_per_day: schedule.shoot_settings?.max_hours_per_day || 10,
    total_budget: budget.total_budget || 100000,
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function save(event) {
    event.preventDefault();
    setSaving(true);
    setError("");
    try {
      const updated = await api.updateProductionSettings(state.project_id, {
        ...form,
        excluded_states: form.excluded_states
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        min_hours_per_day: Number(form.min_hours_per_day),
        max_hours_per_day: Number(form.max_hours_per_day),
        total_budget: Number(form.total_budget),
      });
      setState(updated);
      onSaved?.(updated);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={save} className="stack">
      <div className="form-grid">
        <label className="field">
          <span className="mono-label">Country</span>
          <input className="input" value={form.country} onChange={set("country")} />
        </label>
        <label className="field">
          <span className="mono-label">Exclude states</span>
          <input className="input" placeholder="NV, TX" value={form.excluded_states} onChange={set("excluded_states")} />
        </label>
        <label className="field">
          <span className="mono-label">First shoot day</span>
          <input className="input" type="date" value={form.start_date} onChange={set("start_date")} />
        </label>
        <label className="field">
          <span className="mono-label">Min hours / day</span>
          <input className="input" type="number" min="1" value={form.min_hours_per_day} onChange={set("min_hours_per_day")} />
        </label>
        <label className="field">
          <span className="mono-label">Max hours / day</span>
          <input className="input" type="number" min="1" value={form.max_hours_per_day} onChange={set("max_hours_per_day")} />
        </label>
        <label className="field">
          <span className="mono-label">Total budget</span>
          <input className="input" type="number" min="0" value={form.total_budget} onChange={set("total_budget")} />
        </label>
      </div>
      {error && (
        <div className="banner" data-tone="bad" role="alert">
          <Icon name="error" />
          <span>{error}</span>
        </div>
      )}
      <div className="form-actions">
        <button type="submit" className="btn btn--primary" disabled={saving || !state}>
          <Icon name={saving ? "progress_activity" : "save"} className={saving ? "spin" : undefined} />
          {saving ? "Reconfiguring…" : "Save and reconfigure"}
        </button>
      </div>
    </form>
  );
}
