// Flat cine-camera illustration (vector recreation of the team's reference image):
// grey-purple body with darker grip, pentaprism hump, pale mauve lens ring,
// light-blue glass with a crescent highlight. Drawn in a 168x104 space
// (lens center at 104,62 — that circle doubles as the "o" of CineNode).
export function CameraArt() {
  return (
    <g>
      <rect x="30" y="12" width="18" height="14" rx="3" fill="#3f3a43" />
      <rect x="118" y="15" width="24" height="11" rx="3" fill="#3f3a43" />
      <path d="M56 26 q3 -14 16 -14 h16 q13 0 16 14 z" fill="#4c4650" />
      <rect x="2" y="24" width="164" height="76" rx="14" fill="#5a5460" />
      <path d="M2 38 a14 14 0 0 1 14 -14 h24 v76 h-24 a14 14 0 0 1 -14 -14 z" fill="#49434e" />
      <circle cx="104" cy="62" r="32" fill="#b9aab5" />
      <circle cx="104" cy="62" r="25" fill="#49434e" />
      <circle cx="104" cy="62" r="20" fill="#eaf7fd" />
      <circle cx="108" cy="66" r="17.5" fill="#c8e8f6" />
      <circle cx="150" cy="42" r="3.5" fill="#3f3a43" />
      <circle cx="151" cy="80" r="3" fill="#3f3a43" />
      <circle cx="19" cy="84" r="3" fill="#3f3a43" />
    </g>
  );
}

// Standalone square icon (cover page, avatars...).
export default function CameraIcon({ size = 64 }) {
  return (
    <svg viewBox="0 -28 168 168" width={size} height={size} role="img" aria-label="CineNode camera" style={{ display: "block" }}>
      <CameraArt />
    </svg>
  );
}
