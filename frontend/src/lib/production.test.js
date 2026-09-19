/**
 * The words the sign-off queue puts on screen.
 *
 * The agents leave queue items like `cast_signoff:ROLE_LEAD` and reasons that
 * older runs wrote as codes. The Overview has to read as English, name the
 * role or scene a person actually recognises, and link to the page where the
 * decision is made — so this is what `signOffs` is checked on.
 */
import { describe, expect, it } from "vitest";

import { agentTrace, sampleOutput, signOffs } from "./production.js";

function state(escalations, overrides = {}) {
  return {
    role_requirements: { ROLE_LEAD: { name: "Mara Ellis" }, ROLE_SUPPORT: { name: "Theo Vance" } },
    schedule: { stripboard: [{ scene_id: "SCN_004", title: "The rooftop toast", venue: "Sunset Rooftop" }] },
    audience_report: { scene_titles: { SCN_009: "The last call" } },
    human_escalations: escalations.map(([queue_item, reason = ""]) => ({ queue_item, reason })),
    ...overrides,
  };
}

const only = (escalation) => signOffs(state([escalation]))[0];

describe("what each kind of sign-off says", () => {
  it("names the role a casting decision is about", () => {
    const item = only(["cast_signoff:ROLE_LEAD", "Two candidates within one point of each other"]);

    expect(item.title).toBe("Confirm who plays Mara Ellis");
    expect(item.kicker).toBe("Casting");
    expect(item.action).toBe("Casting board");
    expect(item.to).toBe("/casting");
  });

  it("names the scene a venue or a recut is about", () => {
    expect(only(["venue:SCN_004"]).title).toBe("No venue for “The rooftop toast”");
    expect(only(["recut:SCN_009"]).title).toBe("Recut “The last call”");
    expect(only(["recut:SCN_009"]).to).toBe("/audience");
  });

  it("falls back to the scene's number when nothing has titled it", () => {
    expect(only(["venue:SCN_012"]).title).toBe("No venue for “Scene 12”");
  });

  it("names the territory a release is blocked in", () => {
    expect(only(["compliance:UAE"]).title).toBe("Release blocked in UAE");
    expect(only(["compliance:FR"]).title).toBe("Release blocked in France");
    expect(only(["compliance:ZZ"]).title).toBe("Release blocked in ZZ");
  });

  it("says plainly when the schedule or the launch needs a person", () => {
    expect(only(["schedule:past_wrap"]).title).toBe("The shoot runs past the wrap date");
    expect(only(["schedule:cast"]).title).toBe("Scenes booked on days their cast is away");
    expect(only(["asset:AST_2"]).title).toBe("A campaign post was held back");
    expect(only(["phase4_halt"]).title).toBe("Planning stopped early");
  });

  it("still shows a queue item it has never seen before", () => {
    const item = only(["weather:day_3", "Storm warning"]);

    expect(item.title).toBe("Weather day 3");
    expect(item.kicker).toBe("Decision");
    expect(item.to).toBe("/logs"); // the agent log is where an unknown item can be read
  });
});

describe("the reason underneath", () => {
  it("turns an older run's codes and arrows into a sentence", () => {
    const item = only(["schedule:cast", "SCN_004 -> ROLE_LEAD unavailable"]);

    expect(item.reason).toBe("Scn 004 → role lead unavailable.");
  });

  it("uses curly quotes and leaves an existing sentence alone", () => {
    expect(only(["venue:SCN_004", 'No venue matched "rooftop".']).reason).toBe("No venue matched “rooftop”.");
    expect(only(["venue:SCN_004", "Every rooftop was booked."]).reason).toBe("Every rooftop was booked.");
  });

  it("drops a trailing blob of data", () => {
    const reason = "Two roles unfilled: [{\"role\": \"ROLE_LEAD\"}]";

    expect(only(["cast_signoff:ROLE_LEAD", reason]).reason).toBe("Two roles unfilled.");
  });

  it("is empty rather than invented when the agent gave none", () => {
    expect(only(["compliance:UAE"]).reason).toBe("");
  });
});

describe("the order they are shown in", () => {
  it("puts casting first and an unknown kind last, whatever order they arrived in", () => {
    const items = signOffs(state([
      ["asset:AST_2"], ["weather:day_3"], ["compliance:UAE"], ["cast_signoff:ROLE_LEAD"], ["venue:SCN_004"],
    ]));

    expect(items.map((i) => i.kicker)).toEqual(["Casting", "Schedule", "Release", "Launch", "Decision"]);
    expect(new Set(items.map((i) => i.key)).size).toBe(5); // each row needs a key of its own
  });

  it("is empty for a production with nothing waiting", () => {
    expect(signOffs(state([]))).toEqual([]);
    expect(signOffs(null)).toEqual([]);
  });
});

describe("saying when a plan is Lumen's sample output", () => {
  it("counts the steps that fell back and why", () => {
    const note = sampleOutput({
      model_use: {
        phase1: { live: 0, sample: 6, reason: "no_api_key" },
        phase2: { live: 2, sample: 1, reason: "no_api_key" },
      },
    });

    expect(note.sample).toBe(7);
    expect(note.steps).toBe(9);
    expect(note.why).toMatch(/no Gemini key/);
    expect(note.fix).toMatch(/GEMINI_API_KEY/);
  });

  it("says when the producer's own screenplay went unread", () => {
    const unread = { model_use: { phase1: { live: 0, sample: 6, sample_script: true } } };

    expect(sampleOutput(unread).script).toBe(true);
  });

  it("says nothing when the model answered every step", () => {
    expect(sampleOutput({ model_use: { phase1: { live: 6, sample: 0 } } })).toBeNull();
    expect(sampleOutput({})).toBeNull();
  });
});

/**
 * The execution trace.
 *
 * It is the page's answer to "is anything actually happening", so its numbers
 * have to come from the run rather than from a plausible-looking constant.
 * These check that it counts real envelopes, groups them by the phase the
 * backend stamped, and claims a negotiation loop fired only when the log shows
 * one did.
 */
describe("agentTrace", () => {
  const phases = [
    { key: "phase3", title: "Script to schedule", status: "complete" },
    { key: "phase6", title: "Marketing", status: "running" },
  ];
  const envelope = (phase, sender, intent, payload = {}) => ({ phase, sender, intent, payload });

  it("groups messages by the phase the backend stamped, not by agent name", () => {
    const [three, six] = agentTrace(phases, [
      envelope("phase3", "agent_scheduler_shoot", "check_venue_availability"),
      envelope("phase3", "agent_location", "venue_offer"),
      envelope("phase6", "agent_visual", "asset_status_update"),
    ]);

    expect(three.messages).toBe(2);
    expect(three.agents).toEqual(["agent_location", "agent_scheduler_shoot"]);
    expect(six.messages).toBe(1);
  });

  it("shows a venue negotiation only when a scene was asked about twice", () => {
    const once = [envelope("phase3", "agent_scheduler_shoot", "check_venue_availability", { scene_id: "SCN_001" })];
    expect(agentTrace(phases, once)[0].loops).toEqual([]);

    const loops = agentTrace(phases, [...once, once[0]])[0].loops;
    expect(loops).toHaveLength(1);
    expect(loops[0].pair).toBe("scheduler_shoot ⇄ location");
    expect(loops[0].detail).toMatch(/^1 scene was re-offered/);
  });

  it("counts the extra rounds, not the scenes that had them", () => {
    const events = ["SCN_001", "SCN_001", "SCN_001", "SCN_002", "SCN_002"].map((scene_id) =>
      envelope("phase3", "agent_scheduler_shoot", "check_venue_availability", { scene_id })
    );
    // SCN_001 was re-asked twice and SCN_002 once: three extra rounds.
    expect(agentTrace(phases, events)[0].loops[0].detail).toMatch(/^3 scenes were re-offered/);
  });

  it("reports a redraft only when the block actually triggered a retry", () => {
    // A blocked press release goes to a person. That is an escalation, not a loop.
    const escalated = [envelope("phase6", "agent_copywriter", "asset_status_update", {
      status: "BLOCKED", blocker_details: { auto_retry: false },
    })];
    expect(agentTrace(phases, escalated)[1].loops).toEqual([]);

    const retried = [envelope("phase6", "agent_visual", "asset_status_update", {
      status: "BLOCKED", blocker_details: { auto_retry: true },
    })];
    expect(agentTrace(phases, retried)[1].loops[0].pair).toBe("visual ⇄ pr_risk");
  });

  it("shows every phase as pending before a run has started", () => {
    const rows = agentTrace(null, []);
    expect(rows).toHaveLength(6);
    expect(rows.every((row) => row.status === "pending" && row.messages === 0)).toBe(true);
    expect(rows[0].words).toMatch(/actors/);
  });

  it("survives a run whose event log has not been loaded yet", () => {
    const rows = agentTrace(phases, undefined);
    expect(rows.map((row) => row.messages)).toEqual([0, 0]);
    expect(rows[1].status).toBe("running");
  });

  it("ignores other phases' events and anything logged outside a phase", () => {
    const rows = agentTrace(phases, [
      envelope("phase1", "agent_profiler", "mandate_ready"),
      { sender: "agent_advisor", intent: "mandate_ready", payload: {} },
    ]);
    expect(rows.map((row) => row.messages)).toEqual([0, 0]);
  });
});
