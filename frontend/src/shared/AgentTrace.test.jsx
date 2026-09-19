/**
 * The execution trace on screen.
 *
 * `agentTrace` is tested on its arithmetic in lib/production.test.js; this is
 * about what a producer actually sees. The trace runs during a live plan and
 * again on a finished one, so the cases that matter are the incomplete ones:
 * a run with no traffic loaded yet must still render its phases, and a page
 * with no run at all must not crash or invent activity.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import AgentTrace from "./AgentTrace.jsx";

const PHASES = [
  { key: "phase1", title: "Pre-casting", status: "complete" },
  { key: "phase3", title: "Script to schedule", status: "running" },
  { key: "phase6", title: "Marketing", status: "pending" },
];

const envelope = (phase, sender, intent, payload = {}) => ({ phase, sender, intent, payload });

function trace() {
  return document.querySelector(".agent-trace");
}

it("renders a row for every phase, in the words a producer reads", () => {
  render(<AgentTrace phases={PHASES} status="running" />);

  expect(screen.getByText("Finding actors for each role")).toBeInTheDocument();
  expect(screen.getByText("Booking shoot days and venues")).toBeInTheDocument();
  expect(screen.getByText("Planning the launch")).toBeInTheDocument();
  expect(trace().querySelectorAll(".trace-phase")).toHaveLength(3);
});

it("marks each phase with its own status, not the run's", () => {
  render(<AgentTrace phases={PHASES} status="running" />);
  const rows = trace().querySelectorAll(".trace-phase");

  expect(rows[0].className).toContain("trace-phase--complete");
  expect(rows[1].className).toContain("trace-phase--running");
  expect(rows[2].className).toContain("trace-phase--pending");
});

it("counts the phases done, so progress is legible without reading the rows", () => {
  render(<AgentTrace phases={PHASES} status="running" />);
  expect(screen.getByText(/1 of 3 phases/)).toBeInTheDocument();
});

it("renders while a run is in flight and its traffic has not loaded", () => {
  // The status poll returns phases long before the event log is fetched. This
  // is the state a producer stares at for most of a run.
  render(<AgentTrace phases={PHASES} status="running" />);

  expect(trace().querySelectorAll(".trace-agent")).toHaveLength(0);
  expect(screen.queryByText(/messages/)).not.toBeInTheDocument();
  expect(screen.getByText("Booking shoot days and venues")).toBeInTheDocument();
});

it("names the agents that spoke, once the log is there", () => {
  render(
    <AgentTrace
      phases={PHASES}
      status="complete"
      events={[
        envelope("phase1", "agent_casting_scout", "scout_local_talent"),
        envelope("phase1", "agent_pr_shield", "disqualify"),
        envelope("phase1", "agent_casting_scout", "crawl_locality_completed"),
      ]}
    />
  );
  const first = trace().querySelectorAll(".trace-phase")[0];

  // Two agents spoke, three times between them.
  expect(within(first).getByText("3 messages")).toBeInTheDocument();
  expect(first.querySelectorAll(".trace-agent")).toHaveLength(2);
  expect(within(first).getByTitle("agent_casting_scout")).toBeInTheDocument();
});

it("shows a negotiation loop on the phase that ran it", () => {
  render(
    <AgentTrace
      phases={PHASES}
      status="complete"
      events={[
        envelope("phase3", "agent_scheduler_shoot", "check_venue_availability", { scene_id: "SCN_004" }),
        envelope("phase3", "agent_scheduler_shoot", "check_venue_availability", { scene_id: "SCN_004" }),
      ]}
    />
  );
  const loops = trace().querySelectorAll(".trace-loop");

  expect(loops).toHaveLength(1);
  expect(loops[0].textContent).toContain("scheduler_shoot ⇄ location");
  expect(loops[0].textContent).toContain("re-offered another day");
});

it("shows no loop when none fired", () => {
  render(
    <AgentTrace
      phases={PHASES}
      status="complete"
      events={[envelope("phase3", "agent_scheduler_shoot", "check_venue_availability", { scene_id: "SCN_004" })]}
    />
  );
  expect(trace().querySelectorAll(".trace-loop")).toHaveLength(0);
});

it("falls back to the six phases when there is no run record at all", () => {
  render(<AgentTrace />);

  expect(trace().querySelectorAll(".trace-phase")).toHaveLength(6);
  expect(screen.getByText(/0 of 6 phases/)).toBeInTheDocument();
  expect(screen.queryByText(/messages/)).not.toBeInTheDocument();
});

it("says when a run failed", () => {
  render(<AgentTrace phases={[{ key: "phase1", status: "failed" }]} status="failed" />);

  expect(screen.getByText("failed")).toBeInTheDocument();
  expect(trace().querySelector(".trace-phase").className).toContain("trace-phase--failed");
});

it("takes a caller's title", () => {
  render(<AgentTrace phases={PHASES} title="Execution trace" />);
  expect(screen.getByText("Execution trace")).toBeInTheDocument();
});
