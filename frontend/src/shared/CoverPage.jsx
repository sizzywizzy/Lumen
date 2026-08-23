import { useState } from "react";
import CineNodeLogo from "./CineNodeLogo.jsx";

const PROJECTS = [
  { id: "PROJ_NEON_NIGHTS", title: "Neon Nights", detail: "Cyberpunk thriller · In production", status: "ACTIVE" },
  { id: "PROJ_SILENT_HARBOR", title: "Silent Harbor", detail: "Mystery drama · Pre-production", status: "DRAFT" },
  { id: "PROJ_LAST_SIGNAL", title: "The Last Signal", detail: "Sci-fi short · Ready to launch", status: "READY" },
];

export default function CoverPage({ onEnter }) {
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");

  function createProject(event) {
    event.preventDefault();
    const cleanTitle = title.trim();
    if (!cleanTitle) return;
    const id = `PROJ_${cleanTitle.toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_|_$/g, "")}`;
    onEnter(id);
  }

  return (
    <div className="cover">
      <CineNodeLogo height={72} />
      <div className="project-heading">
        <p className="eyebrow">CINENODE STUDIO</p>
        <h1>Choose a project</h1>
        <p className="tagline">Pick up where you left off, or start a new film workspace.</p>
      </div>
      <div className="project-actions">
        <section className="project-option">
          <div className="option-heading">
            <div><span className="option-number">01</span><h2>Work on existing project</h2></div>
            <span className="option-count">{PROJECTS.length} MOCK PROJECTS</span>
          </div>
          <div className="project-list">
            {PROJECTS.map((project) => (
              <button key={project.id} className="project-card" onClick={() => onEnter(project.id)}>
                <span className="project-mark">{project.title.slice(0, 1)}</span>
                <span className="project-copy"><strong>{project.title}</strong><small>{project.detail}</small></span>
                <span className={`project-status ${project.status.toLowerCase()}`}>{project.status}</span>
                <span className="project-arrow">→</span>
              </button>
            ))}
          </div>
        </section>
        <section className="project-option new-project-option">
          <div className="option-heading">
            <div><span className="option-number">02</span><h2>New project</h2></div>
          </div>
          {creating ? (
            <form className="new-project-form" onSubmit={createProject}>
              <label htmlFor="project-title">Project title</label>
              <input id="project-title" autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="e.g. Midnight Frequency" />
              <div className="form-actions"><button type="button" className="quiet-button" onClick={() => setCreating(false)}>Cancel</button><button className="primary" type="submit" disabled={!title.trim()}>Create project →</button></div>
            </form>
          ) : (
            <button className="new-project-button" onClick={() => setCreating(true)}><span className="plus">+</span><span><strong>Start with a blank workspace</strong><small>Set up your film from script to launch.</small></span><span className="project-arrow">→</span></button>
          )}
        </section>
      </div>
      <footer>Agentic Cinema · Multi-agent film production workspace</footer>
    </div>
  );
}
