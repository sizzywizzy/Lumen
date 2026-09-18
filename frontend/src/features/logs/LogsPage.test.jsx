/**
 * The Live Agent Terminal reads the log a page at a time.
 *
 * A production's state carries only the latest envelopes; everything before
 * them is fetched here, 500 at a time, from /api/events. A full run is over a
 * hundred messages and a re-planned production is thousands, so the paging,
 * the count under the terminal and the filters are what this page has to get
 * right.
 */
import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import LogsPage, { readLog } from "./LogsPage.jsx";

const api = vi.hoisted(() => ({ getEvents: vi.fn() }));
const project = vi.hoisted(() => ({ value: {} }));

vi.mock("../../lib/api.js", () => ({ api }));
vi.mock("../../shared/ProjectContext.jsx", () => ({ useProject: () => project.value }));

const PAGE = 500;

function envelope(index) {
  return {
    message_id: `msg_${index}`,
    sender: index % 2 ? "agent_scout" : "agent_pr_shield",
    recipient: "agent_director_orchestrator",
    intent: "task_status_update",
    timestamp: "2026-09-18T15:45:12Z",
    payload: { index },
  };
}

/** The log the server holds, answered page by page the way /api/events does. */
function serverHolds(total) {
  const all = Array.from({ length: total }, (_, i) => envelope(i));
  api.getEvents.mockImplementation(async (_projectId, since, limit) => ({
    total,
    offset: since,
    events: all.slice(since, since + limit),
  }));
  return all;
}

async function show() {
  render(<LogsPage />);
  await act(async () => {});
}

const countLine = () => screen.getByText(/envelopes/).textContent;

beforeEach(() => {
  project.value = {
    events: [envelope(9000), envelope(9001)], // the latest ones, carried on the state
    revealed: 2,
    eventOffset: 0,
    running: false,
    projectId: "PROJ_NEON_NIGHTS",
    runPipeline: vi.fn(),
    canEdit: true,
  };
  api.getEvents.mockResolvedValue({ total: 0, offset: 0, events: [] });
});

describe("the earlier messages", () => {
  it("are not fetched at all when the state already carries the whole log", async () => {
    await show();

    expect(api.getEvents).not.toHaveBeenCalled();
    expect(countLine()).toMatch(/^2 of 2 envelopes/);
  });

  // The pager itself is checked without the page around it: a production with
  // a long log is thousands of envelopes, and rendering them all to count the
  // requests would make this file the slowest thing in CI.
  it("are read a page at a time up to the first one the state carries", async () => {
    serverHolds(1200);

    const log = await readLog("PROJ_NEON_NIGHTS", 1200);

    expect(api.getEvents.mock.calls.map(([, since, limit]) => [since, limit])).toEqual([
      [0, PAGE],
      [PAGE, PAGE],
      [1000, 200],
    ]);
    expect(log).toHaveLength(1200);
  });

  it("stop being asked for when a page comes back empty", async () => {
    api.getEvents.mockResolvedValueOnce({ total: 900, offset: 0, events: [envelope(0)] })
      .mockResolvedValue({ total: 900, offset: 1, events: [] });

    const log = await readLog("PROJ_NEON_NIGHTS", 900);

    expect(api.getEvents).toHaveBeenCalledTimes(2);
    expect(log).toHaveLength(1);
  });

  it("are put in front of the ones the state carries", async () => {
    serverHolds(3);
    project.value = { ...project.value, eventOffset: 3 };

    await show();

    expect(countLine()).toMatch(/^5 of 5 envelopes/);
  });

  it("say so when they cannot be loaded, without losing the ones in hand", async () => {
    project.value = { ...project.value, eventOffset: 10 };
    api.getEvents.mockRejectedValue(new Error("Can't reach Lumen right now."));

    await show();

    expect(screen.getByRole("alert")).toHaveTextContent("Earlier messages didn't load: Can't reach Lumen right now.");
    expect(countLine()).toMatch(/^2 of 2 envelopes/);
  });

  it("are read again when the production changes", async () => {
    serverHolds(4);
    project.value = { ...project.value, eventOffset: 4 };
    const { rerender } = render(<LogsPage />);
    await act(async () => {});
    const firstRead = api.getEvents.mock.calls.length;

    project.value = { ...project.value, projectId: "PROJ_OTHER" };
    rerender(<LogsPage />);
    await act(async () => {});

    expect(api.getEvents.mock.calls.length).toBeGreaterThan(firstRead);
    expect(api.getEvents.mock.calls.at(-1)[0]).toBe("PROJ_OTHER");
  });
});

describe("what the terminal shows", () => {
  it("counts only the messages revealed so far while a run streams in", async () => {
    project.value = { ...project.value, events: [envelope(1), envelope(2), envelope(3)], revealed: 1, running: true };

    await show();

    expect(countLine()).toMatch(/^1 of 3 envelopes/);
  });

  it("narrows to one agent", async () => {
    project.value = { ...project.value, events: [envelope(1), envelope(2), envelope(3)], revealed: 3 };
    await show();

    await act(async () => {
      const select = screen.getByLabelText("Filter by agent");
      select.value = "agent_scout";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(countLine()).toMatch(/^2 of 3 envelopes/);
  });

  it("holds the stream still while it is paused", async () => {
    project.value = { ...project.value, events: [envelope(1)], revealed: 1 };
    const { rerender } = render(<LogsPage />);
    await act(async () => {});

    await act(async () => {
      screen.getByRole("button", { name: /Pause stream/ }).click();
    });
    project.value = { ...project.value, events: [envelope(1), envelope(2), envelope(3)], revealed: 3 };
    rerender(<LogsPage />);
    await act(async () => {});

    expect(countLine()).toMatch(/^1 of 3 envelopes · stream paused/);

    await act(async () => {
      screen.getByRole("button", { name: /Resume stream/ }).click();
    });

    expect(countLine()).toMatch(/^3 of 3 envelopes/);
  });
});
