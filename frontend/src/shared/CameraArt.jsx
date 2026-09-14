import { useId } from "react";
import { ICON_L } from "./logoGlyphs.js";

// The Lumen camera: a vintage cine camera with two reels, a boxy body and a
// flared lens hood, facing right. It is drawn with the centre of the lens mouth
// at 0,0 so the logo's beam can start exactly there (see assets/logo.svg).
export function CameraArt({ body, glass }) {
  return (
    <g>
      <g style={{ fill: body }}>
        <path fillRule="evenodd" d="M-127 -48a27 27 0 1 0 54 0a27 27 0 1 0 -54 0ZM-107 -48a7 7 0 1 0 14 0a7 7 0 1 0 -14 0Z" />
        <path fillRule="evenodd" d="M-72 -45a22 22 0 1 0 44 0a22 22 0 1 0 -44 0ZM-56 -45a6 6 0 1 0 12 0a6 6 0 1 0 -12 0Z" />
        <rect x="-128" y="-24" width="90" height="50" rx="8" />
        <rect x="-39" y="-9" width="10" height="18" />
        <polygon points="-30,-12 0,-20 0,20 -30,12" />
      </g>
      <rect x="-5" y="-20" width="5" height="40" style={{ fill: glass }} />
    </g>
  );
}

// The square app icon, the same drawing as frontend/public/favicon.svg: the
// camera's beam lighting a gold "L" on a warm ink tile. Its colours are fixed,
// so it reads the same on light and dark surfaces.
export default function LumenIcon({ size = 40 }) {
  const tile = `lumen-tile-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 240 240" width={size} height={size} role="img" aria-label="Lumen" style={{ display: "block" }}>
      <defs>
        <clipPath id={tile}>
          <rect width="240" height="240" rx="52" />
        </clipPath>
      </defs>
      <rect width="240" height="240" rx="52" fill="#2b2018" />
      <path d="M84 79.2 L240 36 L240 232 L84 100.8 Z" fill="#fac33d" fillOpacity="0.22" clipPath={`url(#${tile})`} />
      <path d={ICON_L} fill="#fac33d" />
      <g transform="translate(84 90) scale(0.54)">
        <CameraArt body="#f6a121" glass="#fcde79" />
      </g>
    </svg>
  );
}
