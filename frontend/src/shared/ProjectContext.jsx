import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { useAuth } from "./AuthContext.jsx";

// All pipeline state for the active project lives here so it survives route
// changes — the same GlobalState feeds Casting, Schedule, Marketing and Logs,
// and the terminal replay keeps running while the user moves between pages.
//
// The project id comes from the signed-in member's active production, so a
// user only ever loads a GlobalState their membership grants them.

const REVEAL_MS = 60; // terminal replay speed per message

const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const { activeProjectId, user, canEdit } = useAuth();
  const projectId = activeProjectId;
  const [budget, setBudget] = useState(null); // total budget captured on the intake screen
  const [intake, setIntake] = useState(null); // { budget, start, wrap, notes, fileName }
  const [state, setState] = useState(null);
  const [events, setEvents] = useState([]);
  const [revealed, setRevealed] = useState(0);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const timerRef = useRef(null);

  // Load whatever the backend already has for this project.
  useEffect(() => {
    if (!projectId || !user) {
      setState(null);
      setEvents([]);
      setRevealed(0);
      return undefined;
    }
    let cancelled = false;
    api
      .getState(projectId)
      .then((s) => {
        if (cancelled) return;
        setState(s);
        setEvents(s.event_log);
        setRevealed(s.event_log.length);
      })
      .catch(() => {
        /* no state seeded yet (or backend offline) — the views show empty states */
        if (!cancelled) setState(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, user]);

  useEffect(() => () => clearInterval(timerRef.current), []);

  const runPipeline = useCallback(async () => {
    if (!projectId || !canEdit) {
      setError("Your role on this production is read-only.");
      return;
    }
    setRunning(true);
    setError("");
    setEvents([]);
    setRevealed(0);
    clearInterval(timerRef.current);
    try {
      await api.runPipeline(projectId, budget || undefined);
      const s = await api.getState(projectId);
      setState(s);
      setEvents(s.event_log);
      // Replay the A2A conversation message-by-message in the terminal.
      timerRef.current = setInterval(() => {
        setRevealed((r) => {
          if (r >= s.event_log.length) {
            clearInterval(timerRef.current);
            return r;
          }
          return r + 1;
        });
      }, REVEAL_MS);
    } catch (e) {
      setError(String(e.message || e));
    } finally {
      setRunning(false);
    }
  }, [projectId, budget, canEdit]);

  // Re-read the stored GlobalState, e.g. after a skill run appended agent
  // traffic to the event log on the server.
  const refreshState = useCallback(async () => {
    if (!projectId) return;
    const s = await api.getState(projectId);
    setState(s);
    setEvents(s.event_log);
    setRevealed(s.event_log.length);
  }, [projectId]);

  // Called by the intake screen once the project has been seeded.
  const startProject = useCallback((_nextProjectId, nextIntake) => {
    setIntake(nextIntake || null);
    setBudget(nextIntake?.budget ?? null);
  }, []);

  // Applies a candidate-status change returned by the casting endpoint without
  // a full refetch, so the board updates the moment the request lands.
  const applyCandidateUpdate = useCallback((candidate, castingStatus, eventLog) => {
    setState((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        casting_status: castingStatus ?? prev.casting_status,
        candidates: prev.candidates.map((c) => (c.id === candidate.id ? candidate : c)),
        event_log: eventLog ?? prev.event_log,
      };
    });
    if (eventLog) {
      setEvents(eventLog);
      setRevealed(eventLog.length);
    }
  }, []);

  const value = useMemo(
    () => ({
      projectId,
      budget,
      intake,
      startProject,
      state,
      setState,
      events,
      revealed,
      setRevealed,
      running,
      error,
      setError,
      runPipeline,
      refreshState,
      applyCandidateUpdate,
      canEdit,
    }),
    [projectId, budget, intake, startProject, state, events, revealed, running, error, runPipeline, refreshState, applyCandidateUpdate, canEdit]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used inside <ProjectProvider>");
  return ctx;
}

