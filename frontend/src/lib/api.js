// Thin fetch wrapper for the FastAPI backend (proxied via /api in dev).

// The session token is held here so every request carries it without each
// caller having to remember. AuthContext owns the lifecycle; nothing else
// reads or writes it directly.
const TOKEN_KEY = "cinenode-session";
let sessionToken = null;

export function loadStoredToken() {
  if (sessionToken !== null) return sessionToken;
  try {
    sessionToken = localStorage.getItem(TOKEN_KEY);
  } catch {
    sessionToken = null;
  }
  return sessionToken;
}

export function setSessionToken(token) {
  sessionToken = token || null;
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked — the token still works for this tab's lifetime */
  }
}

// Raised on 401 so the app can bounce the user to the sign-in screen.
export class AuthError extends Error {}

let onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}

// `anonymous` marks the calls that establish a session (sign-in, sign-up):
// no bearer token is attached, and a 401 from them means the credentials
// were rejected, not that a session expired, so the server's own message is
// surfaced instead of the session being dropped.
async function request(path, { anonymous = false, ...options } = {}) {
  const token = anonymous ? null : loadStoredToken();
  const res = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });

  if (res.status === 401 && !anonymous) {
    onUnauthorized?.();
    throw new AuthError("Your session has expired. Sign in again.");
  }

  if (!res.ok) {
    // FastAPI puts the human-readable message in `detail`.
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (Array.isArray(body?.detail)) message = body.detail[0]?.msg || message;
    } catch {
      /* non-JSON error body — keep the status line */
    }
    throw new Error(message);
  }

  if (res.status === 204) return null;
  return res.json();
}

const post = (path, body, extra = {}) =>
  request(path, { method: "POST", body: JSON.stringify(body), ...extra });

export const api = {
  health: () => request("/api/health"),

  // ---- authentication -----------------------------------------------------
  register: (payload) => post("/api/auth/register", payload, { anonymous: true }),
  login: (email, password) => post("/api/auth/login", { email, password }, { anonymous: true }),
  logout: () => post("/api/auth/logout"),
  me: () => request("/api/auth/me"),
  listProjects: () => request("/api/projects"),

  // ---- production team ----------------------------------------------------
  team: (projectId) => request(`/api/auth/team/${projectId}`),
  removeMember: (projectId, userId) =>
    request(`/api/auth/team/${projectId}/${userId}`, { method: "DELETE" }),
  createInvite: (payload) => post("/api/auth/invites", payload),
  listInvites: (projectId) => request(`/api/auth/invites/${projectId}`),
  revokeInvite: (projectId, inviteId) =>
    request(`/api/auth/invites/${projectId}/${inviteId}`, { method: "DELETE" }),
  previewInvite: (token) => request(`/api/auth/invite-preview/${encodeURIComponent(token)}`),
  joinProduction: (payload) => post("/api/auth/join", payload),

  // ---- pipeline + state ---------------------------------------------------
  // Seed a project's state from the cover intake form (budget → casting/venue/reach caps).
  initPipeline: (project_id, budget_usd) =>
    post("/api/pipeline/init", budget_usd ? { project_id, budget_usd } : { project_id }),
  // budget_usd is optional — the backend default applies until the intake form is wired in.
  runPipeline: (project_id, budget_usd) =>
    post("/api/pipeline/run", budget_usd ? { project_id, budget_usd } : { project_id }),
  getState: (projectId) => request(`/api/state/${projectId}`),
  getEvents: (projectId, since = 0) => request(`/api/events/${projectId}?since=${since}`),

  // ---- casting ------------------------------------------------------------
  // Move a candidate along the funnel. Producer/owner only; writes to the
  // shared GlobalState so the whole team sees the decision.
  setCandidateStatus: (projectId, candidateId, status, reason = "") =>
    request(`/api/casting/candidates/${projectId}/${candidateId}`, {
      method: "PATCH",
      body: JSON.stringify({ status, reason }),
    }),

  // ---- audience simulation (Phase V) --------------------------------------
  // Runs execute on a background thread server-side; start returns immediately
  // and the detail route is polled for per-stage progress.
  startSimulation: (projectId, payload) => post(`/api/audience/simulations/${projectId}`, payload),
  listSimulations: (projectId) => request(`/api/audience/simulations/${projectId}`),
  getSimulation: (projectId, simulationId) =>
    request(`/api/audience/simulations/${projectId}/${simulationId}`),
  getSimulationPanel: (projectId, simulationId, offset = 0, limit = 50) =>
    request(`/api/audience/simulations/${projectId}/${simulationId}/panel?offset=${offset}&limit=${limit}`),

  // ---- screenplay ---------------------------------------------------------
  // Stores the script dropped at intake on the shared GlobalState, so Phase V
  // (and anything else) analyses the real screenplay rather than a logline.
  uploadScript: (projectId, payload) => post(`/api/production/script/${projectId}`, payload),
  getScript: (projectId) => request(`/api/production/script/${projectId}`),

  // ---- agent skills (skills/<name>/SKILL.md) --------------------------------
  // A run executes on a background thread; poll the run list until it settles.
  listSkills: () => request("/api/skills"),
  getSkill: (name) => request(`/api/skills/${encodeURIComponent(name)}`),
  runSkill: (name, projectId, params = {}) =>
    post(`/api/skills/${encodeURIComponent(name)}/run/${projectId}`, { params }),
  listSkillRuns: (projectId) => request(`/api/skills/runs/${projectId}`),
  getSkillRun: (projectId, runId) => request(`/api/skills/runs/${projectId}/${runId}`),

  // ---- production ---------------------------------------------------------
  updateProductionSettings: (projectId, settings) =>
    request(`/api/production/settings/${projectId}`, { method: "PUT", body: JSON.stringify(settings) }),
  addExpense: (projectId, expense) => post(`/api/production/expenses/${projectId}`, expense),
  updateShootDay: (projectId, update) => post(`/api/production/shoot-day/${projectId}`, update),
};
