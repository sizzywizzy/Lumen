// CineNode wordmark — the "o" of Node is the team's flat camera illustration:
// the lens lands exactly where the o belongs, the body nestles between N and d.
// Same geometry as assets/logo.svg. textLength on "CineN" is load-bearing —
// it pins where the camera starts.
import { CameraArt } from "./CameraArt.jsx";

const letterStyle = {
  font: "700 76px 'Segoe UI', Inter, system-ui, sans-serif",
  letterSpacing: "-1px",
  fill: "var(--text)",
};

export default function CineNodeLogo({ height = 30 }) {
  return (
    <svg
      viewBox="8 24 466 78"
      height={height}
      role="img"
      aria-label="CineNode"
      style={{ display: "block" }}
    >
      <text x="24" y="95" textLength="212" lengthAdjust="spacingAndGlyphs" style={letterStyle}>
        CineN
      </text>
      <g transform="translate(240 20.6) scale(0.744)">
        <CameraArt />
      </g>
      <text x="370" y="95" style={letterStyle}>
        de
      </text>
    </svg>
  );
}
