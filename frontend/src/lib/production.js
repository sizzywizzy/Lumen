// Turns a production's GlobalState into what the results pages show, in words:
// shoot days with scene names, the cast grouped by role, the budget picture and
// the test screening. Every page (and the homepage example) reads through here,
// so ids like SCN_004 or ROLE_LEAD never reach the screen.
import { initials, shortDate } from "./utils.js";
import { castProfile } from "./castProfiles.js";

const SETTING = { INT: "Interior", EXT: "Exterior", "INT/EXT": "Interior and exterior", "EXT/INT": "Exterior and interior" };
const DAY_MS = 86400000;

const total = (items, pick) => items.reduce((sum, item) => sum + (Number(pick(item)) || 0), 0);

// Calendar dates are read at noon so no timezone moves them to another day.
const asDate = (iso) => new Date(`${iso}T12:00:00`);
const toIso = (date) =>
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;

export function capitalize(text) {
  const value = String(text || "").trim();
  return value ? value[0].toUpperCase() + value.slice(1) : "";
}

export function hoursText(hours) {
  const n = Number(hours) || 0;
  return `${Number.isInteger(n) ? n : n.toFixed(1)} ${n === 1 ? "hour" : "hours"}`;
}

// "Tue, Sep 1"
export function dayLabel(iso) {
  const date = asDate(iso);
  if (Number.isNaN(date.getTime())) return String(iso || "");
  return date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

export const weekdayShort = (iso) => asDate(iso).toLocaleDateString("en-US", { weekday: "short" });
export const dayOfMonth = (iso) => asDate(iso).getDate();

// "Sep 1 – 8, 2026", "Sep 28 – Oct 3, 2026", or a single day.
export function dateRange(first, last) {
  if (!first) return "";
  if (!last || first === last) return shortDate(first);
  const a = asDate(first);
  const b = asDate(last);
  if (a.getFullYear() !== b.getFullYear()) return `${shortDate(first)} – ${shortDate(last)}`;
  const month = (d) => d.toLocaleDateString("en-US", { month: "short" });
  const end = a.getMonth() === b.getMonth() ? b.getDate() : `${month(b)} ${b.getDate()}`;
  return `${month(a)} ${a.getDate()} – ${end}, ${a.getFullYear()}`;
}

export function sceneNumber(sceneId) {
  const match = /(\d+)\s*$/.exec(String(sceneId || ""));
  return match ? Number(match[1]) : null;
}

export function sceneName(entry) {
  if (entry?.title) return entry.title;
  const n = sceneNumber(entry?.scene_id);
  return n ? `Scene ${n}` : "A scene";
}

export function roleName(state, roleId) {
  return state?.role_requirements?.[roleId]?.name || "An unnamed role";
}

export function hasResults(state) {
  return Boolean(
    state?.schedule?.stripboard?.length || state?.candidates?.length || Number(state?.audience_report?.tomatometer)
  );
}

export function productionTitle(state, fallback) {
  return state?.script_context?.title || fallback || "Your production";
}

// Why a plan carries Lumen's sample output instead of the model's. The
// backend counts each phase's calls in `model_use` (core/orchestrator/graph.py).
const SAMPLE_REASONS = {
  no_api_key: "the server has no Gemini key",
  all_models_failed: "Gemini didn't answer",
};
const SAMPLE_FIXES = {
  no_api_key: "Set GEMINI_API_KEY on the server and plan again.",
  all_models_failed: "Its free daily limit may be used up. Try again later.",
};

export function sampleOutput(state) {
  const phases = Object.values(state?.model_use || {}).filter((use) => use && typeof use === "object");
  const count = (key) => phases.reduce((total, use) => total + (Number(use[key]) || 0), 0);
  const sample = count("sample");
  if (!sample) return null;
  const reason = phases.map((use) => use.reason).find(Boolean) || "all_models_failed";
  return {
    sample,
    steps: sample + count("live"),
    // the whole plan describes Lumen's sample film, not the stored screenplay
    script: phases.some((use) => use.sample_script === true),
    why: SAMPLE_REASONS[reason] || SAMPLE_REASONS.all_models_failed,
    fix: SAMPLE_FIXES[reason] || SAMPLE_FIXES.all_models_failed,
  };
}

// ---------------------------------------------------------------- schedule ---

export function shootDays(state) {
  const byDate = new Map();
  for (const entry of state?.schedule?.stripboard || []) {
    if (!byDate.has(entry.date)) byDate.set(entry.date, []);
    byDate.get(entry.date).push(entry);
  }
  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, entries]) => ({
      date,
      hours: total(entries, (e) => e.estimated_time_hours),
      scenes: entries.map((e) => ({
        id: e.scene_id,
        number: sceneNumber(e.scene_id),
        name: sceneName(e),
        titled: Boolean(e.title),
        setting: SETTING[String(e.int_ext || "").toUpperCase()] || "",
        intExt: String(e.int_ext || "").toUpperCase(),
        hours: Number(e.estimated_time_hours) || 0,
        venue: e.venue || "",
        locationType: e.location_type || "",
        heading: e.heading || "",
        summary: e.summary || "",
        timeOfDay: timeOfDay(e.heading),
        status: e.status || "PLANNED",
        note: e.director_note || "",
        costPerDay: Number(e.cost_per_day) || 0,
        roleIds: e.characters_needed || [],
        cast: (e.characters_needed || []).map((roleId) => roleName(state, roleId)),
      })),
    }));
}

// "EXT. NEON DISTRICT STREET - NIGHT" -> "night". Sluglines end in the time of
// day; anything unusual (CONTINUOUS, LATER) reads as unknown.
export function timeOfDay(heading) {
  const h = String(heading || "").toUpperCase();
  if (/\b(DAWN|SUNRISE|EARLY MORNING)\b/.test(h)) return "dawn";
  if (/\b(DUSK|SUNSET|EVENING|MAGIC HOUR|GOLDEN HOUR)\b/.test(h)) return "dusk";
  if (/\bNIGHT\b/.test(h)) return "night";
  if (/\b(DAY|MORNING|AFTERNOON|NOON)\b/.test(h)) return "day";
  return "";
}

// 7 -> "7:00 AM", 13.5 -> "1:30 PM". Call times on the schedule are counted
// from a 7:00 AM call, scene after scene.
export function clockLabel(hour) {
  const total = Math.round((Number(hour) || 0) * 60);
  const h24 = Math.floor(total / 60) % 24;
  const minutes = String(total % 60).padStart(2, "0");
  const h12 = h24 % 12 || 12;
  return `${h12}:${minutes} ${h24 < 12 ? "AM" : "PM"}`;
}

// Scenes the scheduler had to move, by scene id, so a day's list can say so
// next to the scene instead of only in the summary of changes.
export function sceneMoves(state) {
  const moves = new Map();
  for (const c of state?.schedule?.conflicts || []) {
    if (c?.scene_id && c.moved_to) moves.set(c.scene_id, c);
  }
  return moves;
}

// Who plays each role: roleId -> { role, actor } (actor is null until a pick
// is locked). The schedule shows the actor's face next to the character.
export function castLookup(state) {
  const lookup = {};
  for (const role of castByRole(state)) lookup[role.roleId] = { role: role.name, actor: role.pick };
  return lookup;
}

// Every day from the first shoot day to the last, rest days included, for the
// chart. A long shoot falls back to shoot days only so the bars stay readable.
export function calendarDays(days, limit = 21) {
  if (!days.length) return [];
  const hoursByDate = Object.fromEntries(days.map((d) => [d.date, d.hours]));
  const first = asDate(days[0].date);
  const span = Math.round((asDate(days[days.length - 1].date) - first) / DAY_MS) + 1;
  if (span > limit) return days.map((d) => ({ date: d.date, hours: d.hours }));
  return Array.from({ length: span }, (_, i) => {
    const iso = toIso(new Date(first.getTime() + i * DAY_MS));
    return { date: iso, hours: hoursByDate[iso] || 0 };
  });
}

export function scheduleStats(state) {
  const entries = state?.schedule?.stripboard || [];
  const days = shootDays(state);
  const venueDays = new Map(); // a venue is hired once per day, however many scenes shoot there
  for (const e of entries) venueDays.set(`${e.date}|${e.venue}`, Number(e.cost_per_day) || 0);
  return {
    days,
    scenes: entries.length,
    shootDays: days.length,
    hours: total(entries, (e) => e.estimated_time_hours),
    venueCost: total([...venueDays.values()], (v) => v),
    venues: new Set(entries.map((e) => e.venue)).size,
    first: days[0]?.date || null,
    last: days[days.length - 1]?.date || null,
  };
}

// Why a scene landed on a different day than it wanted, as sentences.
export function scheduleChanges(state) {
  const entries = state?.schedule?.stripboard || [];
  return (state?.schedule?.conflicts || [])
    .filter((c) => c.wanted && c.moved_to && c.wanted !== c.moved_to)
    .map((c) => {
      // Newer runs write the reason as a sentence; older ones named agents, so rebuild those.
      if (c.resolution && !/agent_/.test(c.resolution)) return c.resolution;
      const entry = entries.find((e) => e.scene_id === c.scene_id);
      const name = c.title || sceneName(entry || { scene_id: c.scene_id });
      const venue = c.venue || entry?.venue;
      const because = venue ? `, when ${venue} was free` : "";
      return `${name} moved from ${dayLabel(c.wanted)} to ${dayLabel(c.moved_to)}${because}.`;
    });
}

// -------------------------------------------------------------------- cast ---

// "Budget: quote $33,800 exceeds…" -> "Quote $33,800 exceeds…."
function plainReason(reason) {
  const text = String(reason || "").replace(/^(budget|pr)\s*:\s*/i, "").trim();
  if (!text) return "No reason was recorded.";
  return capitalize(text) + (/[.!?]$/.test(text) ? "" : ".");
}

export function actor(candidate) {
  const disqualified = candidate.status === "DISQUALIFIED";
  // photos, credits and background for the Cast page (see castProfiles.js)
  const profile = castProfile(candidate);
  return {
    // a headshot when there is one (metadata.headshot_url); initials otherwise
    photo: profile.headshot?.thumb || null,
    profile,
    id: candidate.id,
    name: candidate.name,
    initials: initials(candidate.name),
    fee: Number(candidate.metadata?.quote_usd) || 0,
    fit: Math.round(Number(candidate.scores?.composite) || 0),
    place: candidate.metadata?.locality || "",
    why: candidate.metadata?.qualitative_review || candidate.metadata?.director_match || "",
    isPick: candidate.status === "LOCKED",
    ruledOut: disqualified,
    reason: disqualified ? plainReason(candidate.disqualify_reason) : "",
  };
}

export function castByRole(state) {
  const roles = state?.role_requirements || {};
  const candidates = state?.candidates || [];
  const roleIds = Object.keys(roles);
  for (const c of candidates) if (c.role_id && !roleIds.includes(c.role_id)) roleIds.push(c.role_id);

  return roleIds.map((roleId) => {
    const people = candidates.filter((c) => c.role_id === roleId);
    const inRunning = people
      .filter((c) => c.status !== "DISQUALIFIED")
      .sort((a, b) => (Number(b.scores?.composite) || 0) - (Number(a.scores?.composite) || 0));
    const pick = inRunning.find((c) => c.status === "LOCKED") || null;
    return {
      roleId,
      name: roleName(state, roleId),
      type: capitalize(roles[roleId]?.type),
      description: capitalize(roles[roleId]?.description),
      pick: pick && actor(pick),
      runnersUp: inRunning.filter((c) => c !== pick).map(actor),
      ruledOut: people.filter((c) => c.status === "DISQUALIFIED").map(actor),
    };
  });
}

export function budgetSummary(state) {
  const cap = Number(state?.budget_state?.cap) || 0;
  const stats = scheduleStats(state);
  const picks = castByRole(state)
    .filter((role) => role.pick)
    .map((role) => ({ role: role.name, ...role.pick }));
  const castFees = total(picks, (p) => p.fee);
  return {
    cap,
    picks,
    castFees,
    venueCost: stats.venueCost,
    venues: stats.venues,
    shootDays: stats.shootDays,
    remaining: cap - castFees - stats.venueCost,
  };
}

// ---------------------------------------------------------------- audience ---

export function screening(state) {
  const report = state?.audience_report;
  const tomatometer = Number(report?.tomatometer) || 0;
  if (!report || !(tomatometer || Number(report.audience_score))) return null;

  const viewers = Number(report.viewer_count) || 200;
  const liked = Math.round((tomatometer / 100) * viewers);
  const entries = state?.schedule?.stripboard || [];
  const nameOf = (id) =>
    report.scene_titles?.[id] || sceneName(entries.find((e) => e.scene_id === id) || { scene_id: id });

  const scenes = Object.entries(report.heatmap || {})
    .map(([id, score]) => ({ id, name: nameOf(id), score: Number(score) || 0, lowest: id === report.weakest_scene_id }))
    .sort((a, b) => (sceneNumber(a.id) ?? 0) - (sceneNumber(b.id) ?? 0));

  const weakestId = report.weakest_scene_id;
  const weakestEntry = entries.find((e) => e.scene_id === weakestId);
  return {
    viewers,
    liked,
    notLiked: viewers - liked,
    tomatometer: Math.round(tomatometer),
    audienceScore: Math.round(Number(report.audience_score) || 0),
    fresh: report.verdict ? report.verdict === "fresh" : tomatometer >= 60,
    scenes,
    weakest: weakestId
      ? {
          name: report.weakest_scene_title || nameOf(weakestId),
          number: sceneNumber(weakestId),
          score: Number(report.heatmap?.[weakestId]) || 0,
          venue: weakestEntry?.venue || "",
        }
      : null,
    reviews: Array.isArray(report.reviews) ? report.reviews : [],
  };
}

// -------------------------------------------------------------- the run ---

// What each phase of a pipeline run is doing, as a producer would say it.
const PHASE_WORDS = {
  phase1: "Finding actors for each role",
  phase2: "Reviewing the auditions",
  phase3: "Booking shoot days and venues",
  phase4: "Checking each territory's rules",
  phase5: "Screening the story with test viewers",
  phase6: "Planning the launch",
};

export function phaseWords(key) {
  return PHASE_WORDS[key] || "Working";
}

// ------------------------------------------------------------------ trace ---
// What the agents actually did, phase by phase, read off the A2A event log.
// Every number here is counted from real envelopes: the backend stamps the
// phase on each one as it is logged (core/messaging/envelope.py), so nothing
// below has to infer a phase from an agent's name — a mapping that would go
// stale the moment an agent moved phase.

export const PHASE_ORDER = ["phase1", "phase2", "phase3", "phase4", "phase5", "phase6"];

// Lumen has exactly two negotiation loops, and each leaves a specific trace.
// A single round trip is just a request; the loop is the *extra* passes, so
// that is what these count. No extra passes, no loop shown.
function venueRenegotiations(events) {
  const askedPerScene = {};
  for (const event of events) {
    if (event.intent !== "check_venue_availability") continue;
    const scene = event.payload?.scene_id || "";
    askedPerScene[scene] = (askedPerScene[scene] || 0) + 1;
  }
  return Object.values(askedPerScene).reduce((sum, times) => sum + Math.max(0, times - 1), 0);
}

// Only agent_visual redraws on a block. A blocked press release sets
// auto_retry false and goes to a person, so it is not a loop and is not
// counted as one.
function blockedRedrafts(events) {
  return events.filter(
    (event) =>
      event.intent === "asset_status_update" &&
      event.payload?.status === "BLOCKED" &&
      event.payload?.blocker_details?.auto_retry === true
  ).length;
}

/**
 * One row per phase: its status, who spoke, how much, and which loops fired.
 *
 * `phases` is the run record the dashboard polls (key, title, status) and
 * `events` is GlobalState.event_log. Either may be missing: before a run there
 * is no record, and while one is in flight its traffic has not been loaded
 * yet, so the row falls back to status alone rather than to invented detail.
 */
export function agentTrace(phases, events = []) {
  const logged = Array.isArray(events) ? events : [];
  const rows = (phases || []).length
    ? phases.map((p) => ({ key: p.key, title: p.title || "", status: p.status || "pending" }))
    : PHASE_ORDER.map((key) => ({ key, title: "", status: "pending" }));

  return rows.map((phase) => {
    const mine = logged.filter((event) => event.phase === phase.key);
    const loops = [];
    if (phase.key === "phase3") {
      const rounds = venueRenegotiations(mine);
      if (rounds) {
        loops.push({
          pair: "scheduler_shoot ⇄ location",
          detail: `${rounds} ${rounds === 1 ? "scene was" : "scenes were"} re-offered another day`,
        });
      }
    }
    if (phase.key === "phase6") {
      const blocked = blockedRedrafts(mine);
      if (blocked) {
        loops.push({
          pair: "visual ⇄ pr_risk",
          detail: `${blocked} ${blocked === 1 ? "draft was" : "drafts were"} blocked and redrawn`,
        });
      }
    }
    return {
      ...phase,
      words: phaseWords(phase.key),
      messages: mine.length,
      agents: [...new Set(mine.map((event) => event.sender))].sort(),
      loops,
    };
  });
}

// ---------------------------------------------------------------- sign-off ---

const TERRITORIES = { US: "US", UK: "UK", UAE: "UAE", FR: "France", IN: "India", JP: "Japan" };

function quotedScene(state, sceneId) {
  const entry = (state?.schedule?.stripboard || []).find((e) => e.scene_id === sceneId);
  const title = state?.audience_report?.scene_titles?.[sceneId] || sceneName(entry || { scene_id: sceneId });
  return `“${title}”`;
}

// What the agents are waiting for a person to decide
// (GlobalState.human_escalations), and where on the site to decide it.
const SIGN_OFF_KINDS = [
  {
    test: (id) => id.startsWith("cast_signoff:"),
    icon: "how_to_reg", kicker: "Casting", action: "Casting board", to: "/casting",
    title: (arg, state) => `Confirm who plays ${roleName(state, arg)}`,
  },
  {
    test: (id) => id === "schedule:past_wrap",
    icon: "event_busy", kicker: "Schedule", action: "Production desk", to: "/production",
    title: () => "The shoot runs past the wrap date",
  },
  {
    test: (id) => id === "schedule:cast",
    icon: "person_off", kicker: "Schedule", action: "Production desk", to: "/production",
    title: () => "Scenes booked on days their cast is away",
  },
  {
    test: (id) => id.startsWith("venue:"),
    icon: "location_off", kicker: "Schedule", action: "Production desk", to: "/production",
    title: (arg, state) => `No venue for ${quotedScene(state, arg)}`,
  },
  {
    test: (id) => id.startsWith("compliance:"),
    icon: "gpp_bad", kicker: "Release", action: "Clearances", to: "/production",
    title: (arg) => `Release blocked in ${TERRITORIES[arg] || arg}`,
  },
  {
    test: (id) => id.startsWith("recut:"),
    icon: "movie_edit", kicker: "Edit", action: "Test screening", to: "/audience",
    title: (arg, state) => `Recut ${quotedScene(state, arg)}`,
  },
  {
    test: (id) => id.startsWith("asset:"),
    icon: "campaign", kicker: "Launch", action: "Launch desk", to: "/marketing",
    title: () => "A campaign post was held back",
  },
  {
    test: (id) => /^phase\d_halt$/.test(id),
    icon: "pan_tool", kicker: "Pipeline", action: "Agent log", to: "/logs",
    title: () => "Planning stopped early",
  },
];

// Older saved states wrote some reasons as codes or raw data; newer runs write sentences.
function plainSentence(reason) {
  const text = String(reason || "")
    .replace(/:\s*\[\{.*\}\]\s*$/s, "")
    .replace(/\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g, (code) => code.replace(/_/g, " ").toLowerCase())
    .replace(/\s*->\s*/g, " → ")
    .replace(/"([^"]+)"/g, "“$1”")
    .trim();
  if (!text) return "";
  return capitalize(text) + (/[.!?)”"]$/.test(text) ? "" : ".");
}

// Grouped by kind in the order above (casting first), whatever order the
// phases raised them in.
export function signOffs(state) {
  const rank = (item) => {
    const at = SIGN_OFF_KINDS.findIndex((k) => k.test(String(item.queue_item || "")));
    return at === -1 ? SIGN_OFF_KINDS.length : at;
  };
  const items = [...(state?.human_escalations || [])].sort((a, b) => rank(a) - rank(b));
  return items.map((item, index) => {
    const id = String(item.queue_item || "");
    const arg = id.includes(":") ? id.slice(id.indexOf(":") + 1) : "";
    const kind = SIGN_OFF_KINDS.find((k) => k.test(id));
    return {
      key: `${index}-${id}`,
      icon: kind?.icon || "pending_actions",
      kicker: kind?.kicker || "Decision",
      title: kind ? kind.title(arg, state) : capitalize(id.replace(/[_:]+/g, " ")),
      reason: plainSentence(item.reason),
      action: kind?.action || "Agent log",
      to: kind?.to || "/logs",
    };
  });
}
