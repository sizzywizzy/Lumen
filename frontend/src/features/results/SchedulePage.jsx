import Icon from "../../shared/Icon.jsx";
import { useAuth } from "../../shared/AuthContext.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { money } from "../../lib/utils.js";
import { dateRange, hasResults, scheduleChanges, scheduleStats } from "../../lib/production.js";
import { Card, DayBars, Legend, NoPlanYet, ShootDays, Stat } from "./parts.jsx";

export default function SchedulePage() {
  const { state } = useProject();
  const { canEdit } = useAuth();
  if (!hasResults(state)) return <NoPlanYet canEdit={canEdit} />;

  const stats = scheduleStats(state);
  const changes = scheduleChanges(state);

  return (
    <>
      <div className="page-top">
        <div>
          <h1>Shoot schedule</h1>
          <p>
            {stats.first
              ? `${dateRange(stats.first, stats.last)} · ${stats.scenes} scenes over ${stats.shootDays} shoot days`
              : "No shoot days have been planned yet."}
          </p>
        </div>
      </div>

      <div className="dash-grid">
        <Card className="col-8" title="Hours on set">
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

        <Card className="col-12" title="Day by day">
          <div style={{ marginTop: 20 }}>
            <ShootDays days={stats.days} />
          </div>
        </Card>
      </div>
    </>
  );
}
