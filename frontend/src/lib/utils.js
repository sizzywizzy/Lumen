// Tiny classname helper (Tailwind-style cn(), no deps).
export function cn(...parts) {
  return parts.filter(Boolean).join(" ");
}

// Backwards-compatible colour lookup for any caller still reading raw colours.
export const STATUS_COLORS = {
  LOCKED: "var(--status-success)",
  CLEARED: "var(--status-success)",
  APPROVED: "var(--status-success)",
  SCHEDULED: "var(--status-success)",
  POSTED: "var(--status-success)",
  SCREENING: "var(--status-warning)",
  AWAITING_QC: "var(--status-warning)",
  PR_REVIEW: "var(--status-warning)",
  FLAGGED_ACTION_REQUIRED: "var(--status-warning)",
  DRAFT: "var(--on-surface-variant)",
  SOURCING: "var(--on-surface-variant)",
  BLOCKED: "var(--status-error)",
  DISQUALIFIED: "var(--status-error)",
};

// Semantic tone for every backend status literal. Drives pill colour, lamps,
// meters and score bars so status hierarchy is consistent across all screens.
const STATUS_TONES = {
  LOCKED: "ok",
  CLEARED: "ok",
  APPROVED: "ok",
  SCHEDULED: "ok",
  POSTED: "ok",
  COMPLETED: "ok",
  SCREENING: "warn",
  AWAITING_QC: "warn",
  PR_REVIEW: "warn",
  PARTIAL: "warn",
  FLAGGED_ACTION_REQUIRED: "warn",
  DRAFT: "neutral",
  SOURCING: "neutral",
  PLANNED: "neutral",
  BLOCKED: "bad",
  DISQUALIFIED: "bad",
};

export function statusTone(status) {
  return STATUS_TONES[status] || "neutral";
}

// What each backend status literal means, in words a producer would use.
const STATUS_WORDS = {
  LOCKED: "Top pick",
  CLEARED: "Cleared",
  APPROVED: "Approved",
  SCHEDULED: "Scheduled",
  POSTED: "Posted",
  COMPLETED: "Done",
  SCREENING: "In review",
  AWAITING_QC: "Awaiting checks",
  PR_REVIEW: "In PR review",
  PARTIAL: "Partly done",
  FLAGGED_ACTION_REQUIRED: "Needs attention",
  DRAFT: "Draft",
  SOURCING: "Searching",
  PLANNED: "Planned",
  BLOCKED: "Blocked",
  DISQUALIFIED: "Ruled out",
};

// Sentence case for anything without a mapping: "SOME_NEW_STATE" -> "Some new state".
function sentence(value) {
  const words = String(value || "").replace(/[_-]+/g, " ").trim().toLowerCase();
  return words ? words[0].toUpperCase() + words.slice(1) : "";
}

export function statusLabel(status) {
  return STATUS_WORDS[status] || sentence(status);
}

// "producer" -> "Producer"
export function roleLabel(role) {
  return sentence(role);
}

export function money(value) {
  return `$${Math.round(Number(value) || 0).toLocaleString("en-US")}`;
}

// 1.2M / 340k / 940 — for tight table cells and gauge captions.
export function compactMoney(value) {
  const n = Number(value) || 0;
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (Math.abs(n) >= 1_000) return `$${Math.round(n / 1_000)}k`;
  return `$${Math.round(n)}`;
}

export function clampPercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, n));
}

// Initials for the avatar placeholders in the casting leaderboard.
export function initials(name) {
  return String(name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join("");
}

// "2026-09-01" or an ISO timestamp -> "Sep 1, 2026".
export function shortDate(value) {
  if (!value) return "";
  const text = String(value);
  // a bare date is a calendar day; read it at noon so no timezone shifts it
  const date = /^\d{4}-\d{2}-\d{2}$/.test(text) ? new Date(`${text}T12:00:00`) : new Date(text);
  if (Number.isNaN(date.getTime())) return text;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

// "2026-09-04T10:42:07Z" -> "10:42:07" for terminal timestamps.
export function clockTime(iso) {
  const m = /T(\d{2}:\d{2}:\d{2})/.exec(String(iso || ""));
  if (m) return m[1];
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "--:--:--" : d.toTimeString().slice(0, 8);
}
