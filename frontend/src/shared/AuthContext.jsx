import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, loadStoredToken, setSessionToken, setUnauthorizedHandler } from "../lib/api.js";

// Owns the signed-in user, their productions, and the active production.
// The bearer token lives in lib/api.js; this context never exposes it to
// components, so no screen can leak it into markup or a URL.

const AuthContext = createContext(null);
const ACTIVE_KEY = "cinenode-active-project";

function readActiveProject() {
  try {
    return localStorage.getItem(ACTIVE_KEY);
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [productions, setProductions] = useState([]);
  const [activeProjectId, setActive] = useState(readActiveProject);
  const [ready, setReady] = useState(false);

  const clear = useCallback(() => {
    setSessionToken(null);
    setUser(null);
    setProductions([]);
    setActive(null);
    try {
      localStorage.removeItem(ACTIVE_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  // Any 401 from anywhere in the app drops the session.
  useEffect(() => {
    setUnauthorizedHandler(() => clear());
    return () => setUnauthorizedHandler(null);
  }, [clear]);

  // Restore the session on load, if the stored token is still valid.
  useEffect(() => {
    if (!loadStoredToken()) {
      setReady(true);
      return;
    }
    api
      .me()
      .then(({ user: u, productions: p }) => {
        setUser(u);
        setProductions(p);
      })
      .catch(() => clear())
      .finally(() => setReady(true));
  }, [clear]);

  const adoptSession = useCallback((payload) => {
    setSessionToken(payload.token);
    setUser(payload.user);
    setProductions(payload.productions || []);
    const first = payload.productions?.[0]?.project_id || null;
    setActive((current) => {
      const stillValid = payload.productions?.some((p) => p.project_id === current);
      return stillValid ? current : first;
    });
  }, []);

  const selectProduction = useCallback((projectId) => {
    setActive(projectId);
  }, []);

  useEffect(() => {
    try {
      if (activeProjectId) localStorage.setItem(ACTIVE_KEY, activeProjectId);
    } catch {
      /* ignore */
    }
  }, [activeProjectId]);

  // Keep the active production pointing at something the user can actually open.
  useEffect(() => {
    if (!productions.length) return;
    if (!productions.some((p) => p.project_id === activeProjectId)) {
      setActive(productions[0].project_id);
    }
  }, [productions, activeProjectId]);

  const login = useCallback(
    async (email, password) => adoptSession(await api.login(email, password)),
    [adoptSession]
  );

  const register = useCallback(
    async (payload) => adoptSession(await api.register(payload)),
    [adoptSession]
  );

  const join = useCallback(async (payload) => adoptSession(await api.joinProduction(payload)), [adoptSession]);

  const logout = useCallback(async () => {
    try {
      await api.logout(); // revokes the session server-side
    } catch {
      /* already gone — clear locally regardless */
    }
    clear();
  }, [clear]);

  const refresh = useCallback(async () => {
    const { user: u, productions: p } = await api.me();
    setUser(u);
    setProductions(p);
  }, []);

  const activeProduction = useMemo(
    () => productions.find((p) => p.project_id === activeProjectId) || null,
    [productions, activeProjectId]
  );

  const value = useMemo(
    () => ({
      user,
      productions,
      activeProduction,
      activeProjectId: activeProduction?.project_id || null,
      role: activeProduction?.role || null,
      canEdit: activeProduction?.role === "owner" || activeProduction?.role === "producer",
      isOwner: activeProduction?.role === "owner",
      ready,
      login,
      register,
      join,
      logout,
      refresh,
      selectProduction,
    }),
    [user, productions, activeProduction, ready, login, register, join, logout, refresh, selectProduction]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
