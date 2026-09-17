// Thin fetch wrapper for the FastAPI backend (proxied via /api in dev).

// Where the API lives. Empty keeps every call relative (/api/...), which is
// what dev (Vite proxy) and any same-origin host need. A frontend hosted apart
// from the API sets VITE_API_URL at build time, e.g.
// VITE_API_URL=https://lumen-api.onrender.com
const API_URL = (import.meta.env.VITE_API_URL || "").trim().replace(/\/+$/, "");

// The session token is held here so every request carries it without each
// caller having to remember. AuthContext owns the lifecycle; nothing else
// reads or writes it directly.
const TOKEN_KEY = "lumen-session";
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
// Plain-language fallback for a failed request that carries no message of its own.
function fallbackMessage(status) {
  if (status === 403) return "You don't have permission to do that on this production.";
  if (status === 404) return "We couldn't find that. It may have been removed.";
  if (status === 413) return "That file is too large to upload.";
  if (status === 429) return "That's a lot of requests at once. Wait a moment and try again.";
  if (status >= 500) return "Something went wrong on our side. Please try again in a moment.";
  return "That didn't work. Please try again.";
}

// `blob` returns the body as a Blob, for images that need the session token
// (an <img src> cannot send it).
async function request(path, { anonymous = false, blob = false, ...options } = {}) {
  const token = anonymous ? null : loadStoredToken();
  let res;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
    });
  } catch {
    throw new Error("Can't reach Lumen right now. Check your connection and try again.");
  }

  if (res.status === 401 && !anonymous) {
    onUnauthorized?.();
    throw new AuthError("Your session has expired. Sign in again.");
  }

  if (!res.ok) {
    // FastAPI puts the human-readable message in `detail`.
    let message = fallbackMessage(res.status);
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (Array.isArray(body?.detail)) message = String(body.detail[0]?.msg || message).replace(/^Value error,\s*/, "");
    } catch {
      /* non-JSON error body — keep the plain-language fallback */
    }
    throw new Error(message);
  }

  if (res.status === 204) return null;
  return blob ? res.blob() : res.json();
}

const post = (path, body, extra = {}) =>
  request(path, { method: "POST", body: JSON.stringify(body), ...extra });

const pipelineBody = (project_id, budget_usd, locality, director_notes, start_date, end_date) => ({
  project_id,
  budget_usd: budget_usd ? Number(budget_usd) : undefined,
  locality: locality || undefined,
  director_notes: director_notes || undefined,
  start_date: start_date || undefined,
  end_date: end_date || undefined,
});

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
  // Seed a project's state from the script drop form (budget → casting/venue/reach
  // caps, locality, director notes, shooting dates as YYYY-MM-DD).
  initPipeline: (project_id, budget_usd, locality, director_notes, start_date, end_date) =>
    post("/api/pipeline/init", pipelineBody(project_id, budget_usd, locality, director_notes, start_date, end_date)),
  // Runs work in the background: this returns the run's record at once, and
  // pipelineStatus reports each phase until it is "complete" or "failed".
  runPipeline: (project_id, budget_usd, locality, director_notes, start_date, end_date) =>
    post("/api/pipeline/run", pipelineBody(project_id, budget_usd, locality, director_notes, start_date, end_date)),
  pipelineStatus: (projectId) => request(`/api/pipeline/status/${projectId}`),
  // The state carries only the latest envelopes (event_offset says where they
  // start); the full log is read a page at a time.
  getState: (projectId) => request(`/api/state/${projectId}`),
  getEvents: (projectId, since = 0, limit = 500) =>
    request(`/api/events/${projectId}?since=${since}&limit=${limit}`),

  // ---- casting ------------------------------------------------------------
  // Move a candidate along the funnel. Producer/owner only; writes to the
  // shared GlobalState so the whole team sees the decision.
  setCandidateStatus: (projectId, candidateId, status, reason = "") =>
    request(`/api/casting/candidates/${projectId}/${candidateId}`, {
      method: "PATCH",
      body: JSON.stringify({ status, reason }),
    }),
  // Re-run the talent scout and auditions (background, like runPipeline) with
  // an optional new locality and notes.
  runCasting: (projectId, payload = {}) => post(`/api/casting/run/${projectId}`, payload),

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

  // ---- poster ---------------------------------------------------------------
  // A pipeline run on a new screenplay paints its poster on a background
  // thread; poll getPoster while it says "painting". The image is fetched once
  // per poster id, which is also what keeps a cached copy from going stale.
  getPoster: (projectId) => request(`/api/launch/poster/${projectId}`),
  newPoster: (projectId) => post(`/api/launch/poster/${projectId}`, {}),
  getPosterImage: (projectId, posterId) =>
    request(`/api/launch/poster/${projectId}/image?v=${encodeURIComponent(posterId)}`, { blob: true }),

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
