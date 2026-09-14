// Neon Nights, Lumen's built-in sample production, shaped like a real
// GlobalState so the homepage example renders through the same helpers as the
// results pages. Fees, fit scores, shoot days, venues and screening scores come
// from the backend's offline sample run; scene titles and the audience quotes
// are the plain-language additions the results pages show.

const LA = "Los Angeles, CA";

export const SAMPLE_STATE = {
  script_context: {
    title: "Neon Nights",
    genre: "neo-noir thriller",
    logline: "A cab-driving ex-detective chases a deepfake blackmail ring through the city's neon underbelly.",
  },
  role_requirements: {
    ROLE_LEAD: { name: "Mara Voss", type: "lead", description: "An ex-detective in their 30s, weary but sharp." },
    ROLE_ANTAG: { name: "Silas Kade", type: "antagonist", description: "A charismatic deepfake broker in their 40s." },
  },
  candidates: [
    {
      id: "sample-lucia", name: "Lucia Morales", role_id: "ROLE_LEAD", status: "LOCKED",
      scores: { composite: 66.1 },
      metadata: { quote_usd: 15000, locality: LA, director_match: "Winner of Best Actor at the Los Angeles Independent Film Festival, with an expressive screen presence that suits Mara." },
    },
    { id: "sample-evelyn", name: "Evelyn Vance", role_id: "ROLE_LEAD", status: "SCREENING", scores: { composite: 64.4 }, metadata: { quote_usd: 18000, locality: LA } },
    { id: "sample-corinne", name: "Corinne Bailey", role_id: "ROLE_LEAD", status: "SCREENING", scores: { composite: 64.4 }, metadata: { quote_usd: 16200, locality: LA } },
    {
      id: "sample-darius", name: "Darius Thorne", role_id: "ROLE_ANTAG", status: "LOCKED",
      scores: { composite: 62.7 },
      metadata: { quote_usd: 21200, locality: LA, director_match: "A breakout regional performance and a strong local following. Brings gritty intensity and real charisma." },
    },
    {
      id: "sample-caleb", name: "Caleb Sterling", role_id: "ROLE_ANTAG", status: "DISQUALIFIED",
      scores: {}, metadata: { quote_usd: 33800, locality: LA },
      disqualify_reason: "Asking fee of $33,800 is over the $25,000 limit for this role (10% of the budget).",
    },
  ],
  schedule: {
    stripboard: [
      { scene_id: "SCN_001", title: "Rain on the neon strip", date: "2026-09-01", venue: "Lumen District Backlot", int_ext: "EXT", estimated_time_hours: 4, cost_per_day: 2500, characters_needed: ["ROLE_LEAD"] },
      { scene_id: "SCN_002", title: "The passenger's confession", date: "2026-09-01", venue: "Checker Cab Rig", int_ext: "INT", estimated_time_hours: 3, cost_per_day: 900, characters_needed: ["ROLE_LEAD"] },
      { scene_id: "SCN_003", title: "First look at Silas", date: "2026-09-03", venue: "The Neon Lounge", int_ext: "INT", estimated_time_hours: 6, cost_per_day: 1800, characters_needed: ["ROLE_LEAD", "ROLE_ANTAG"] },
      { scene_id: "SCN_004", title: "The rooftop toast", date: "2026-09-03", venue: "Skyline Rooftop Bar", int_ext: "INT", estimated_time_hours: 4, cost_per_day: 2200, characters_needed: ["ROLE_ANTAG"] },
      { scene_id: "SCN_005", title: "Showdown at the warehouse", date: "2026-09-06", venue: "Pier 9 Warehouse", int_ext: "INT", estimated_time_hours: 8, cost_per_day: 1500, characters_needed: ["ROLE_LEAD", "ROLE_ANTAG"] },
      { scene_id: "SCN_006", title: "Dawn at the harbor", date: "2026-09-06", venue: "East Harbor Docks", int_ext: "EXT", estimated_time_hours: 3, cost_per_day: 1200, characters_needed: ["ROLE_LEAD"] },
    ],
    conflicts: [],
  },
  budget_state: { cap: 250000 },
  audience_report: {
    tomatometer: 82.5,
    audience_score: 66.5,
    viewer_count: 200,
    heatmap: { SCN_001: 6.82, SCN_002: 6.87, SCN_003: 6.73, SCN_004: 5.93, SCN_005: 6.86, SCN_006: 6.7 },
    weakest_scene_id: "SCN_004",
    reviews: [
      { source: "The Circuit", score: "4 out of 5", quote: "A rain-slicked stunner. Lucia Morales is a revelation as Mara Voss." },
      { source: "FrameRate Weekly", score: "7 out of 10", quote: "It idles during the rooftop toast, but the finale detonates." },
      { source: "Neon Pulse", score: "B+", quote: "Silas Kade is all charm and menace, the villain of the year." },
      { source: "A viewer aged 25 to 34", score: "8 out of 10", quote: "Mara carries the whole film, and the warehouse showdown is the scene I keep thinking about." },
    ],
  },
};
