import { useAuth } from "../../shared/AuthContext.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { cn } from "../../lib/utils.js";
import { hasResults, productionTitle, screening } from "../../lib/production.js";
import { Card, NoPlanYet, Quotes, ScoreSummary } from "./parts.jsx";

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
          <h1>Test screening</h1>
          <p>{screen ? `${screen.viewers} simulated viewers watched ${title}.` : "The test screening hasn't run yet."}</p>
        </div>
      </div>

      {screen && (
        <div className="dash-grid">
          <Card className="col-5" title="How it scored">
            <div style={{ marginTop: 18 }}>
              <ScoreSummary screen={screen} />
            </div>
          </Card>

          <Card className="col-7" title="Scene by scene">
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
            <Card className="col-12" title="What the test audience said">
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
