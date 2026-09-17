import { useAuth } from "../../shared/AuthContext.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { cn } from "../../lib/utils.js";
import { hasResults, productionTitle, screening } from "../../lib/production.js";
import { PencilNote, Ticket } from "../../shared/Artifacts.jsx";
import { Card, NoPlanYet, Quotes, SampleDataNote, ScoreSummary } from "./parts.jsx";

export default function AudiencePage() {
  const { state } = useProject();
  const { canEdit, activeProduction } = useAuth();
  if (!hasResults(state)) return <NoPlanYet canEdit={canEdit} />;

  const screen = screening(state);
  const title = productionTitle(state, activeProduction?.name);

  return (
    <>
      <div className="page-top">
        <div>
          <p className="page-slug">{title}</p>
          <h1>Test screening</h1>
          <p>{screen ? `${screen.viewers} simulated viewers watched ${title}.` : "The test screening hasn't run yet."}</p>
        </div>
        {screen && <PencilNote className="page-hint">one house, every seat filled</PencilNote>}
      </div>

      <SampleDataNote state={state} />

      {screen && (
        <div className="dash-grid">
          <section className="card card--ticket col-5">
            <Ticket stub={`Admit ${screen.viewers}`}>
              <h2 className="card-title">How it scored</h2>
              <div style={{ marginTop: 18 }}>
                <ScoreSummary screen={screen} />
              </div>
            </Ticket>
          </section>

          <Card className="col-7 card--slate" title="Scene by scene">
            <div className="scene-scores">
              {screen.scenes.map((scene) => (
                <div className={cn("scene-score", scene.lowest && "is-lowest")} key={scene.id}>
                  <div className="scene-score__name">
                    {scene.name}
                    {scene.lowest && <span className="kicker"> · lowest</span>}
                  </div>
                  <div className="scene-score__track">
                    <i style={{ width: `${Math.min(100, scene.score * 10)}%` }} />
                  </div>
                  <div className="scene-score__value">{scene.score.toFixed(1)} / 10</div>
                </div>
              ))}
            </div>
          </Card>

          {screen.reviews.length > 0 && (
            <Card className="col-12 card--clippings" title="What the test audience said">
              <div style={{ marginTop: 18 }}>
                <Quotes reviews={screen.reviews} />
              </div>
            </Card>
          )}
        </div>
      )}
    </>
  );
}
