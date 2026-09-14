// Lumen wordmark: the flat cine-camera mark on the left, the name set beside it.
// Same geometry as assets/logo.svg. textLength on "Lumen" pins the word's width,
// so the layout is identical whichever fallback font ends up rendering it.
import { CameraArt } from "./CameraArt.jsx";

const letterStyle = {
  font: "700 76px 'Segoe UI', Inter, system-ui, sans-serif",
  letterSpacing: "-1px",
  fill: "var(--on-surface)",
};

export default function LumenLogo({ height = 30 }) {
  return (
    <svg
      viewBox="4 24 400 78"
      height={height}
      role="img"
      aria-label="Lumen"
      style={{ display: "block" }}
    >
      <g transform="translate(14 20.6) scale(0.744)">
        <CameraArt />
      </g>
      <text x="156" y="95" textLength="236" lengthAdjust="spacingAndGlyphs" style={letterStyle}>
        Lumen
      </text>
    </svg>
  );
}
