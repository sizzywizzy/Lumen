// One nav definition drives the desktop sidebar, the mobile bottom bar and the
// route table, so navigation can never point at a screen that does not exist.
export const PRIMARY_NAV = [
  { to: "/", label: "Script Intake", short: "Intake", icon: "description", end: true },
  { to: "/casting", label: "Casting", short: "Casting", icon: "groups" },
  { to: "/schedule", label: "Schedule", short: "Schedule", icon: "event_note" },
  { to: "/marketing", label: "Marketing", short: "Launch", icon: "campaign" },
];

export const SECONDARY_NAV = [
  { to: "/logs", label: "Logs", short: "Logs", icon: "terminal" },
  { to: "/team", label: "Team", short: "Team", icon: "diversity_3" },
  { to: "/settings", label: "Settings", short: "Settings", icon: "settings" },
];

// Sub-line shown under each page title. Stage names only — no phase numbering.
export const STAGE_BY_PATH = {
  "/": "Intake",
  "/casting": "Pre-casting & Audition",
  "/schedule": "Schedule & Compliance",
  "/marketing": "Audience & Marketing",
};
