/**
 * Following a pipeline run that works on the server.
 *
 * Starting a run returns at once and the page polls its status until it
 * settles, so most of what can go wrong here is in the waiting: a run that was
 * already going when the page loaded, a run that fails, a server that
 * restarted under it, and a production the user switched away from.
 */
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectProvider, useProject } from "./ProjectContext.jsx";

const api = vi.hoisted(() => ({
  getState: vi.fn(),
  pipelineStatus: vi.fn(),
  runPipeline: vi.fn(),
}));
const auth = vi.hoisted(() => ({ value: {} }));

vi.mock("../lib/api.js", () => ({ api }));
vi.mock("./AuthContext.jsx", () => ({ useAuth: () => auth.value }));

const POLL_MS = 1500;

function stateWith(overrides = {}) {
  return { project_id: "PROJ_NEON_NIGHTS", event_log: [], event_offset: 0, event_count: 0, ...overrides };
}

function running(jobId = "JOB_1") {
  return { job_id: jobId, status: "running", phases: [{ key: "phase1", title: "Pre-casting", status: "running" }] };
}

function complete(jobId = "JOB_1", extra = {}) {
  return { job_id: jobId, status: "complete", log_start: 0, phases: [], ...extra };
}

/** Renders the pieces of the context each test reads. */
function Probe() {
  const { running: isRunning, job, error, events, runPipeline } = useProject();
  return (
    <div>
      <span data-testid="running">{String(isRunning)}</span>
      <span data-testid="job">{job ? `${job.job_id || "-"}:${job.status}` : "none"}</span>
      <span data-testid="error">{error}</span>
      <span data-testid="events">{events.length}</span>
      <button type="button" onClick={runPipeline}>
        Plan it
      </button>
    </div>
  );
}

// The clock is faked, so every wait is driven from here rather than by a real
// one: `settle` drains the requests already in flight and `tick` lets one poll
// interval pass. Testing Library's own waitFor cannot see vitest's fake clock,
// so it is not used in this file.
async function settle(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

async function mount() {
  render(
    <ProjectProvider>
      <Probe />
    </ProjectProvider>
  );
  await settle();
}

const tick = () => settle(POLL_MS);

const shows = (id) => screen.getByTestId(id).textContent;

async function press(label) {
  await act(async () => {
    screen.getByRole("button", { name: label }).click();
  });
  await settle();
}

beforeEach(() => {
  vi.useFakeTimers();
  auth.value = { activeProjectId: "PROJ_NEON_NIGHTS", user: { id: "usr_1" }, canEdit: true };
  api.getState.mockResolvedValue(stateWith());
  api.pipelineStatus.mockResolvedValue({ project_id: "PROJ_NEON_NIGHTS", status: "idle" });
  api.runPipeline.mockResolvedValue(running());
});

describe("a run that was already going when the page loaded", () => {
  it("is followed to the end, and the finished plan is loaded", async () => {
    // Picked up on load, still going one interval later, finished the next.
    api.pipelineStatus
      .mockResolvedValueOnce(running())
      .mockResolvedValueOnce(running())
      .mockResolvedValueOnce(running())
      .mockResolvedValue(complete());
    api.getState
      .mockResolvedValueOnce(stateWith())
      .mockResolvedValue(stateWith({ event_log: [{ sender: "agent_scout" }, { sender: "agent_pr_shield" }] }));

    await mount();
    expect(shows("running")).toBe("true");

    await tick();
    expect(shows("running")).toBe("true");

    await tick();
    expect(shows("running")).toBe("false");
    expect(shows("job")).toBe("JOB_1:complete");
    expect(shows("events")).toBe("2");
    expect(api.getState).toHaveBeenCalledTimes(2);
  });

  it("stops polling once the run has settled", async () => {
    api.pipelineStatus.mockResolvedValueOnce(running()).mockResolvedValue(complete());

    await mount();
    await tick();
    expect(shows("running")).toBe("false");
    const polls = api.pipelineStatus.mock.calls.length;

    await tick();
    await tick();

    expect(api.pipelineStatus.mock.calls.length).toBe(polls);
  });

  it("reports what went wrong when it fails", async () => {
    api.pipelineStatus.mockResolvedValueOnce(running()).mockResolvedValue({
      job_id: "JOB_1", status: "failed", error: "Gemini didn't answer.", phases: [],
    });

    await mount();
    await tick();

    expect(shows("error")).toBe("Gemini didn't answer.");
    expect(shows("running")).toBe("false");
  });

  it("says so when the server restarted and took the run with it", async () => {
    api.pipelineStatus.mockResolvedValueOnce(running("JOB_1")).mockResolvedValue(complete("JOB_2"));

    await mount();
    await tick();

    expect(shows("error")).toMatch(/restarted/i);
  });

  it("is left alone when there is no run to follow", async () => {
    await mount();

    expect(shows("running")).toBe("false");
    expect(shows("job")).toBe("-:idle");
    expect(api.pipelineStatus).toHaveBeenCalledTimes(1);
  });
});

describe("starting a run from a button", () => {
  it("follows it and loads the plan", async () => {
    api.runPipeline.mockResolvedValue(running("JOB_9"));
    api.pipelineStatus.mockResolvedValueOnce({ status: "idle" }).mockResolvedValue(complete("JOB_9"));
    await mount();

    await press("Plan it");

    expect(shows("job")).toBe("JOB_9:complete");
    expect(shows("running")).toBe("false");
    expect(shows("error")).toBe("");
  });

  it("is refused for a read-only role, without asking the server", async () => {
    auth.value = { ...auth.value, canEdit: false };
    await mount();

    await press("Plan it");

    expect(shows("error")).toMatch(/read-only/);
    expect(api.runPipeline).not.toHaveBeenCalled();
  });

  it("drops a run whose production the user moved away from", async () => {
    api.runPipeline.mockResolvedValue(running("JOB_9"));
    api.pipelineStatus.mockResolvedValueOnce({ status: "idle" }).mockImplementation(async () => {
      auth.value = { ...auth.value, activeProjectId: "PROJ_OTHER" };
      return complete("JOB_9");
    });
    await mount();

    await press("Plan it");

    expect(shows("error")).toBe("");
  });
});

describe("a production with nothing stored yet", () => {
  it("shows an empty terminal instead of an error", async () => {
    api.getState.mockRejectedValue(new Error("No state for PROJ_NEON_NIGHTS"));

    await mount();

    expect(shows("events")).toBe("0");
    expect(shows("error")).toBe("");
  });
});
