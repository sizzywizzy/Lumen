import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api.js";
import { useAuth } from "./AuthContext.jsx";

// All pipeline state for the active project lives here so it survives route
// changes — the same GlobalState feeds Casting, Schedule, Marketing and Logs,
// and the terminal replay keeps running while the user moves between pages.
//
// The project id comes from the signed-in member's active production, so a
// user only ever loads a GlobalState their membership grants them.
//
// Pipeline runs work in the background on the server. Starting one returns at
// once; this context polls the run's status until it settles, then reloads
// the state and replays the run's messages in the terminal. A run that was
// already going when the page loaded is picked up the same way.

const REVEAL_MS = 60; // terminal replay speed per message
const POLL_MS = 1500;
const EMPTY_FEED = { events: [], revealed: 0, offset: 0, count: 0 };

// Plain formats are read as text in the browser; anything else (.pdf, .fdx)
// goes up as base64 and the backend extracts it.
const PLAIN_TEXT = /\.(txt|fountain|md|markdown|text)$/i;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function readAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("We couldn't open that file. Try saving it again and dropping it in."));
    reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
    reader.readAsDataURL(file);
  });
}

// Raised when the production changes while a run is being watched: the
// result belongs to the other production, so it is dropped quietly.
class Superseded extends Error {
  constructor() {
    super("You switched productions, so this page stopped following that plan. It keeps going on the server.");
  }
}

const ProjectContext = createContext(null);

export function ProjectProvider({ children }) {
  const { activeProjectId, user, canEdit } = useAuth();
  const projectId = activeProjectId;
  const [budget, setBudget] = useState(null); // total budget captured on the intake screen
  const [locality, setLocality] = useState("Los Angeles, CA");
  const [directorNotes, setDirectorNotes] = useState("");
  const [intake, setIntake] = useState(null); // { budget, start, wrap, notes, locality, fileName }
  const [state, setState] = useState(null);
  // The terminal feed: the latest envelopes, how many are shown so far, where
  // the first one sits in the full log, and how long the full log is.
  const [feed, setFeed] = useState(EMPTY_FEED);
  const [running, setRunning] = useState(false);
  const [job, setJob] = useState(null); // the pipeline run in flight, else the last one
  const [error, setError] = useState("");
  const timerRef = useRef(null);
  const projectRef = useRef(projectId);
  projectRef.current = projectId;

  const stopReplay = () => clearInterval(timerRef.current);

  // Take a freshly loaded state. `replayFrom` is the index in its event_log
  // from which messages are revealed one by one; null shows them all at once.
  const adopt = useCallback((s, replayFrom = null) => {
    setState(s);
    if (s.locality) setLocality(s.locality);
    if (s.director_notes) setDirectorNotes(s.director_notes);
    const events = s.event_log || [];
    stopReplay();
    setFeed({
      events,
      offset: s.event_offset || 0,
      count: s.event_count ?? events.length,
      revealed: replayFrom === null ? events.length : Math.min(Math.max(0, replayFrom), events.length),
    });
    if (replayFrom === null) return;
    timerRef.current = setInterval(() => {
      setFeed((f) => {
        if (f.revealed >= f.events.length) {
          clearInterval(timerRef.current);
          return f;
        }
        return { ...f, revealed: f.revealed + 1 };
      });
    }, REVEAL_MS);
  }, []);

  // Poll the production's run until it settles. Resolves with the finished
  // record; rejects when it failed, or when the server no longer knows it (a
  // restart ends a run in flight).
  const waitForRun = useCallback(async (forProject, jobId, onStatus) => {
    for (;;) {
      if (projectRef.current !== forProject) throw new Superseded();
      const status = await api.pipelineStatus(forProject);
      if (projectRef.current !== forProject) throw new Superseded();
      setJob(status);
      onStatus?.(status);
      if (status.job_id !== jobId) {
        throw new Error("Lumen restarted before this plan was finished. Please run it again.");
      }
      if (status.status === "complete") return status;
      if (status.status === "failed") {
        throw new Error(status.error || "Planning stopped before it finished. Please try again.");
      }
      await sleep(POLL_MS);
    }
  }, []);

  // Start a background run, wait for it, then load the result. The run's own
  // messages replay in the terminal unless `replay` is off.
  const runJob = useCallback(
    async (start, { onStatus, replay = true } = {}) => {
      const forProject = projectId;
      const started = await start();
      setJob(started);
      const done = await waitForRun(forProject, started.job_id, onStatus);
      const s = await api.getState(forProject);
      if (projectRef.current !== forProject) throw new Superseded();
      adopt(s, replay ? (done.log_start ?? 0) - (s.event_offset || 0) : null);
      return s;
    },
    [projectId, waitForRun, adopt]
  );

  // Load whatever the backend already has for this project, and pick up a run
  // that is still going.
  useEffect(() => {
    stopReplay();
    setJob(null);
    setRunning(false);
    if (!projectId || !user) {
      setState(null);
      setFeed(EMPTY_FEED);
      return undefined;
    }
    let cancelled = false;
    api
      .getState(projectId)
      .then((s) => !cancelled && adopt(s))
      .catch(() => {
        /* no state seeded yet (or backend offline) — the views show empty states */
        if (!cancelled) {
          setState(null);
          setFeed(EMPTY_FEED);
        }
      });
    api
      .pipelineStatus(projectId)
      .then(async (status) => {
        if (cancelled) return;
        setJob(status);
        if (status.status !== "running") return;
        setRunning(true);
        try {
          await waitForRun(projectId, status.job_id);
          const s = await api.getState(projectId);
          if (!cancelled) adopt(s);
        } catch (e) {
          if (!cancelled && !(e instanceof Superseded)) setError(String(e.message || e));
        } finally {
          if (!cancelled) setRunning(false);
        }
      })
      .catch(() => {
        /* status is advisory; the page still works without it */
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, user, adopt, waitForRun]);

  useEffect(() => () => clearInterval(timerRef.current), []);

  // Wraps a run started from a button: one at a time, errors shown in the
  // page banner. Returns the new state, or null when it did not finish.
  const guarded = useCallback(
    async (start, { rethrow = false } = {}) => {
      if (!projectId || !canEdit) {
        setError("Your role on this production is read-only.");
        return null;
      }
      setRunning(true);
      setError("");
      try {
        return await runJob(start);
      } catch (e) {
        if (e instanceof Superseded) return null;
        setError(String(e.message || e));
        if (rethrow) throw e;
        return null;
      } finally {
        if (projectRef.current === projectId) setRunning(false);
      }
    },
    [projectId, canEdit, runJob]
  );

  const runPipeline = useCallback(
    () => guarded(() => api.runPipeline(projectId, budget || undefined, locality, directorNotes)),
    [guarded, projectId, budget, locality, directorNotes]
  );

  // Re-run the talent scout and auditions with an updated locality and notes.
  const runCasting = useCallback(
    (customLocality, customNotes) => {
      const targetLocality = customLocality || locality;
      const targetNotes = customNotes !== undefined ? customNotes : directorNotes;
      if (customLocality) setLocality(customLocality);
      if (customNotes !== undefined) setDirectorNotes(customNotes);
      return guarded(
        () => api.runCasting(projectId, { locality: targetLocality, director_notes: targetNotes }),
        { rethrow: true }
      );
    },
    [guarded, projectId, locality, directorNotes]
  );

  // Re-read the stored GlobalState, e.g. after a skill run appended agent
  // traffic to the event log on the server.
  const refreshState = useCallback(async () => {
    if (!projectId) return;
    adopt(await api.getState(projectId));
  }, [projectId, adopt]);

  // The whole drop-a-script flow: seed the production, upload the screenplay,
  // run every phase, then load the results. `onStep` hears "reading" and then
  // "planning" (with the run's progress) as each real step starts, so the
  // progress screen never claims something finished before it has.
  const startRun = useCallback(
    async ({ file, budget: amount, start, wrap, locality: place, notes }, onStep = () => {}) => {
      if (!projectId || !canEdit) throw new Error("Only producers and the owner can drop in a new script.");
      setRunning(true);
      setError("");
      stopReplay();
      try {
        onStep("reading");
        await api.initPipeline(projectId, amount, place, notes, start, wrap);
        try {
          const payload = PLAIN_TEXT.test(file.name)
            ? { filename: file.name, text: await file.text() }
            : { filename: file.name, content_base64: await readAsBase64(file) };
          await api.uploadScript(projectId, payload);
        } catch (e) {
          throw new Error(`We couldn't read that script. ${e.message || ""}`.trim());
        }
        setIntake({ budget: amount, start, wrap, notes, locality: place, fileName: file.name });
        setBudget(amount);
        setLocality(place);
        setDirectorNotes(notes);

        onStep("planning", null);
        return await runJob(() => api.runPipeline(projectId, amount, place, notes, start, wrap), {
          replay: false,
          onStatus: (status) => onStep("planning", status),
        });
      } finally {
        if (projectRef.current === projectId) setRunning(false);
      }
    },
    [projectId, canEdit, runJob]
  );

  // Applies a candidate-status change returned by the casting endpoint without
  // a full refetch, so the board updates the moment the request lands.
  const applyCandidateUpdate = useCallback((candidate, castingStatus, event) => {
    setState((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        casting_status: castingStatus ?? prev.casting_status,
        candidates: prev.candidates.map((c) => (c.id === candidate.id ? candidate : c)),
        event_log: event ? [...prev.event_log, event] : prev.event_log,
        event_count: event ? (prev.event_count ?? prev.event_log.length) + 1 : prev.event_count,
      };
    });
    if (event) {
      stopReplay();
      setFeed((f) => {
        const events = [...f.events, event];
        return { ...f, events, revealed: events.length, count: f.count + 1 };
      });
    }
  }, []);

  const value = useMemo(
    () => ({
      projectId,
      budget,
      locality,
      setLocality,
      directorNotes,
      setDirectorNotes,
      intake,
      state,
      setState,
      events: feed.events,
      revealed: feed.revealed,
      eventOffset: feed.offset,
      eventCount: feed.count,
      running,
      job,
      error,
      setError,
      runPipeline,
      runCasting,
      startRun,
      refreshState,
      applyCandidateUpdate,
      canEdit,
    }),
    [
      projectId,
      budget,
      locality,
      directorNotes,
      intake,
      state,
      feed,
      running,
      job,
      error,
      runPipeline,
      runCasting,
      startRun,
      refreshState,
      applyCandidateUpdate,
      canEdit,
    ]
  );

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

export function useProject() {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used inside <ProjectProvider>");
  return ctx;
}
