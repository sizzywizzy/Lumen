// Intro / cover screen: the brand, the pitch, and a door into any phase.
import CineNodeLogo from "./CineNodeLogo.jsx";

const PHASES = [
  { num: "I", tab: "casting", name: "Pre-Casting Intelligence", desc: "Script + brief become casting mandates; PR and budget risks fail fast." },
  { num: "II", tab: "casting", name: "Audition Analysis", desc: "Tapes crunched and graded — the leaderboard builds itself." },
  { num: "III", tab: "production", name: "Script → Schedule", desc: "Scenes broken down, venues negotiated, stripboard + burn rate." },
  { num: "IV", tab: "production", name: "Compliance & Localization", desc: "Rights cleared per territory; a hard block turns the map red." },
  { num: "V", tab: "launch", name: "Audience Simulation", desc: "Synthetic viewers screen the cut — Tomatometer, heatmap, recut advice." },
  { num: "VI", tab: "launch", name: "Marketing & Social Launch", desc: "Reels, memes and posters — PR-gated and scheduled autonomously." },
];

export default function CoverPage({ onEnter }) {
  return (
    <div className="cover">
      <CineNodeLogo height={72} />
      <p className="tagline">
        One multi-agent studio that takes a film from{" "}
        <strong>script → screen → social launch</strong>. Agents negotiate,
        fail fast and self-correct — humans only sign off at the top.
      </p>
      <button className="primary enter" onClick={() => onEnter("casting")}>
        ▶ Enter the studio
      </button>
      <div className="phase-grid">
        {PHASES.map((p) => (
          <button key={p.num} className="phase-card" onClick={() => onEnter(p.tab)}>
            <div className="num">PHASE {p.num}</div>
            <h4>{p.name}</h4>
            <p>{p.desc}</p>
          </button>
        ))}
      </div>
      <footer>Agentic Cinema: The Blockbuster Hackathon · Google Cloud × Replit track</footer>
    </div>
  );
}
