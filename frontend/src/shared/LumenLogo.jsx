import { useId } from "react";
import { CameraArt } from "./CameraArt.jsx";
import { LUMEN_LETTERS } from "./logoGlyphs.js";

// The Lumen logo: a vintage cine camera whose beam lights up the name. Same
// drawing as assets/logo.svg, but coloured from the --logo-* tokens so it
// follows the app's light/dark setting rather than the operating system's.
const BEAM = "M118 162 L810 36.5 L810 329.75 L118 202 Z";

export default function LumenLogo({ height = 34 }) {
  const beam = `lumen-beam-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="-14 32 828 302" height={height} role="img" aria-label="Lumen" style={{ display: "block" }}>
      <defs>
        <clipPath id={beam}>
          <path d={BEAM} />
        </clipPath>
      </defs>
      <path d={BEAM} style={{ fill: "var(--logo-beam)", fillOpacity: "var(--logo-beam-opacity)" }} />
      <path d={LUMEN_LETTERS} style={{ fill: "var(--logo-unlit)" }} />
      <path d={LUMEN_LETTERS} clipPath={`url(#${beam})`} style={{ fill: "var(--logo-lit)" }} />
      <g transform="translate(118 182)">
        <CameraArt body="var(--logo-camera)" glass="var(--logo-glass)" />
      </g>
    </svg>
  );
}

// Just the name in the logo's lettering, for places that pair it with the square
// icon (the sidebar). The viewBox is the 28px line box of 27px type, so it sits
// where a text heading would, and it takes its colour from the surrounding text.
export function LumenWordmark({ height = 28 }) {
  return (
    <svg viewBox="150 126 612.6 207.4" height={height} role="img" aria-label="Lumen" style={{ display: "block" }}>
      <path d={LUMEN_LETTERS} fill="currentColor" />
    </svg>
  );
}
