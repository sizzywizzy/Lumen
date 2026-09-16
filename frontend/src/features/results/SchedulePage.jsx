import Icon from "../../shared/Icon.jsx";
import { useAuth } from "../../shared/AuthContext.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { money } from "../../lib/utils.js";
import { PencilNote } from "../../shared/Artifacts.jsx";
import { dateRange, hasResults, productionTitle, scheduleChanges, scheduleStats } from "../../lib/production.js";
import { Card, DayBars, Legend, NoPlanYet, Stat } from "./parts.jsx";
import ScheduleBoard from "./ScheduleBoard.jsx";

export default function SchedulePage() {
  const { state } = useProject();
  const { canEdit, activeProduction } = useAuth();
  if (!hasResults(state)) return <NoPlanYet canEdit={canEdit} />;

  const stats = scheduleStats(state);
  const changes = scheduleChanges(state);

  return (
    <>
      <div className="page-top">
        <div>
          <p className="page-slug">{productionTitle(state, activeProduction?.name)}</p>
          <h1>Shoot schedule</h1>
          <p>
            {stats.first
              ? `${dateRange(stats.first, stats.last)} · ${stats.scenes} scenes over ${stats.shootDays} shoot days`
              : "No shoot days have been planned yet."}
          </p>
        </div>
        <PencilNote className="page-hint">pick a day to see it alone</PencilNote>
      </div>

      <div className="dash-grid">
        <Card className="col-8 card--slate" title="Hours on set">
          <div className="stats" style={{ margin: "18px 0 26px" }}>
            <Stat value={stats.shootDays} label="Shoot days" />
            <Stat value={`${stats.hours}h`} label="On set" />
            <Stat value={stats.venues} label="Locations" />
            <Stat value={money(stats.venueCost)} label="Cost to hire the venues" />
          </div>
          {stats.days.length > 0 && (
            <>
              <DayBars days={stats.days} />
              <div style={{ marginTop: 20 }}>
                <Legend items={[["Shooting", false], ["Free time in a 10-hour day", true]]} />
              </div>
            </>
          )}
        </Card>

        <Card className="col-4" title="Changes Lumen made">
          {changes.length ? (
            <ul className="change-list">
              {changes.map((change) => (
                <li key={change}>
                  <Icon name="event_repeat" />
                  <span>{change}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="card-note" style={{ marginTop: 12 }}>
              Every scene got the day it asked for.
            </p>
          )}
        </Card>

        <Card className="col-12" title="Day by day" action={<span className="card-note">Call at 7:00 AM</span>}>
          <div style={{ marginTop: 20 }}>
            <ScheduleBoard state={state} />
          </div>
        </Card>
      </div>
    </>
  );
}
