// Tiny classname helper (Tailwind-style cn(), no deps).
export function cn(...parts) {
  return parts.filter(Boolean).join(" ");
}

export const STATUS_COLORS = {
  LOCKED: "var(--ok)",
  CLEARED: "var(--ok)",
  APPROVED: "var(--ok)",
  SCHEDULED: "var(--ok)",
  POSTED: "var(--ok)",
  SCREENING: "var(--warn)",
  AWAITING_QC: "var(--warn)",
  PR_REVIEW: "var(--warn)",
  DRAFT: "var(--muted)",
  SOURCING: "var(--muted)",
  BLOCKED: "var(--bad)",
  DISQUALIFIED: "var(--bad)",
};
