// Thin fetch wrapper for the FastAPI backend (proxied via /api in dev).

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json();
}

export const api = {
  health: () => request("/api/health"),
  // budget_usd is optional — the backend default applies until the intake form is wired in.
  runPipeline: (project_id, budget_usd) =>
    request("/api/pipeline/run", {
      method: "POST",
      body: JSON.stringify(budget_usd ? { project_id, budget_usd } : { project_id }),
    }),
  getState: (projectId) => request(`/api/state/${projectId}`),
  getEvents: (projectId, since = 0) => request(`/api/events/${projectId}?since=${since}`),
  updateProductionSettings: (projectId, settings) => request(`/api/production/settings/${projectId}`, { method: "PUT", body: JSON.stringify(settings) }),
  addExpense: (projectId, expense) => request(`/api/production/expenses/${projectId}`, { method: "POST", body: JSON.stringify(expense) }),
  updateShootDay: (projectId, update) => request(`/api/production/shoot-day/${projectId}`, { method: "POST", body: JSON.stringify(update) }),
};
