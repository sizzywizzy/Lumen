import { useState } from "react";
import { Link } from "react-router-dom";
import Icon from "../../shared/Icon.jsx";
import { useAuth } from "../../shared/AuthContext.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { cn, money } from "../../lib/utils.js";
import {
  budgetSummary, capitalize, castByRole, dateRange, hasResults, hoursText, productionTitle, scheduleStats, screening,
} from "../../lib/production.js";
import { PencilNote } from "../../shared/Artifacts.jsx";
import { ActorTile, Card, CardLink, DayBars, Legend, NoPlanYet, SampleDataNote, Stat, ViewerBar } from "./parts.jsx";
import ProductionPoster from "./ProductionPoster.jsx";
import SignOffQueue from "./SignOffQueue.jsx";

function MoneyRow({ icon, title, sub, amount, caption, positive = false }) {
  return (
    <div className="money-row">
      <span className="round-icon">
        <Icon name={icon} />
      </span>
      <div className="money-row__main">
        <div className="money-row__title">{title}</div>
        <div className="money-row__sub">{sub}</div>
      </div>
      <div className="money-row__amount">
        <strong className={positive ? "amount-positive" : undefined}>{amount}</strong>
        <small>{caption}</small>
      </div>
    </div>
  );
}

export default function OverviewPage() {
  const { state, projectId } = useProject();
  const { activeProduction, canEdit } = useAuth();
  const [roleFilter, setRoleFilter] = useState("all");

  if (!hasResults(state)) return <NoPlanYet canEdit={canEdit} />;

  const stats = scheduleStats(state);
  const budget = budgetSummary(state);
  const roles = castByRole(state);
  const screen = screening(state);
  const people = roles.flatMap((role) =>
    [role.pick, ...role.runnersUp, ...role.ruledOut].filter(Boolean).map((person) => ({ ...person, role: role.name, roleId: role.roleId }))
  );
  const shown = people.filter((person) => roleFilter === "all" || person.roleId === roleFilter);
  const subtitle = [
    capitalize(state.script_context?.genre),
    stats.first && `Shooting ${dateRange(stats.first, stats.last)}`,
    budget.cap && `Budget ${money(budget.cap)}`,
  ].filter(Boolean);

  return (
    <>
      <div className="page-top page-top--poster">
        <div className="page-top__lead">
          {/* the poster Lumen draws for the script: the title card stands in until it's ready */}
          <ProductionPoster
            projectId={projectId}
            title={productionTitle(state, activeProduction?.name)}
            genre={state.script_context?.genre}
            canEdit={canEdit}
          />
          <div>
            <p className="page-slug">Production file</p>
            <h1>{productionTitle(state, activeProduction?.name)}</h1>
            <p>{subtitle.join(" · ")}</p>
          </div>
        </div>
        {canEdit && (
          <Link to="/team" className="btn btn--ghost">
            <Icon name="group_add" size={18} />
            Invite your team
          </Link>
        )}
      </div>

      <SampleDataNote state={state} />

      <div className="dash-grid">
        <SignOffQueue state={state} className="col-12 card--signoff" />

        <Card className="col-8 card--slate" title="Shoot schedule" action={<CardLink to="/schedule">Full schedule</CardLink>}>
          <div className="stats" style={{ margin: "18px 0 26px" }}>
            <Stat value={stats.scenes} label="Scenes" />
            <Stat value={stats.shootDays} label="Shoot days" />
            <Stat value={`${stats.hours}h`} label="On set" />
            <Stat value={stats.venues} label={stats.venues === 1 ? "Location" : "Locations"} />
          </div>
          {stats.days.length ? (
            <>
              <DayBars days={stats.days} />
              <div style={{ marginTop: 20 }}>
                <Legend items={[["Shooting", false], ["Free time in a 10-hour day", true]]} />
              </div>
            </>
          ) : (
            <p className="card-note">No shoot days have been planned yet.</p>
          )}
        </Card>

        <section className="card card--flush col-4">
          <div className="feature-top">
            <div>
              <div className="stat-value">{money(budget.cap)}</div>
              <div className="stat-label">Total budget</div>
            </div>
          </div>
          <div className="money-list">
            {budget.picks.map((pick) => (
              <MoneyRow key={pick.id} icon="person" title={pick.name} sub={`${pick.role} · top pick`} amount={`−${money(pick.fee)}`} caption="Cast fee" />
            ))}
            <MoneyRow
              icon="location_on"
              title={`${budget.venues} ${budget.venues === 1 ? "location" : "locations"}`}
              sub={`Across ${budget.shootDays} shoot ${budget.shootDays === 1 ? "day" : "days"}`}
              amount={`−${money(budget.venueCost)}`}
              caption="Venue hire"
            />
            <MoneyRow
              icon="account_balance_wallet"
              title="Left to spend"
              sub="After cast and venues"
              amount={money(budget.remaining)}
              caption="Remaining"
              positive={budget.remaining >= 0}
            />
          </div>
        </section>

        <Card className="col-8" title="Cast" action={<CardLink to="/cast">All casting</CardLink>}>
          <div className="tabs" style={{ marginTop: 14 }} role="tablist">
            {[{ roleId: "all", name: "All roles" }, ...roles].map((role) => (
              <button
                key={role.roleId}
                type="button"
                role="tab"
                aria-selected={roleFilter === role.roleId}
                className={cn("tab", roleFilter === role.roleId && "active")}
                onClick={() => setRoleFilter(role.roleId)}
              >
                {role.name}
              </button>
            ))}
          </div>
          {shown.length ? (
            <div className="tiles" style={{ marginTop: 20 }}>
              {shown.map((person) => (
                <ActorTile key={person.id} role={person.role} person={person} />
              ))}
            </div>
          ) : (
            <p className="card-note" style={{ marginTop: 20 }}>No actors have been suggested yet.</p>
          )}
        </Card>

        <div className="col-4 col-stack">
          <Card title="Test screening" action={screen && <span className="chip">{screen.viewers} viewers</span>}>
            {screen ? (
              <>
                <div className="stats" style={{ margin: "16px 0 18px" }}>
                  <Stat value={`${screen.tomatometer}%`} label="Tomatometer" />
                  <Stat value={`${screen.audienceScore}%`} label="Audience score" />
                </div>
                <ViewerBar liked={screen.liked} viewers={screen.viewers} />
                <div style={{ marginTop: 14 }}>
                  <Legend items={[[`Liked it · ${screen.liked}`, false], [`Didn't · ${screen.notLiked}`, true]]} />
                </div>
              </>
            ) : (
              <p className="card-note" style={{ marginTop: 12 }}>The test screening hasn't run yet.</p>
            )}
          </Card>

          {screen?.weakest && (
            <section className="card card--highlight">
              <div className="row row--tight">
                {screen.weakest.number && <span className="chip">Scene {screen.weakest.number}</span>}
                {screen.weakest.venue && (
                  <span className="chip">
                    <Icon name="location_on" />
                    {screen.weakest.venue}
                  </span>
                )}
              </div>
              <h3>Viewers drifted during {screen.weakest.name.startsWith("Scene ") ? screen.weakest.name.toLowerCase() : `“${screen.weakest.name}”`}</h3>
              <p>
                It had the lowest average score of any scene, {screen.weakest.score.toFixed(1)} out of 10 from{" "}
                {screen.viewers} test viewers.
              </p>
              <Link to="/audience" className="btn btn--primary btn--block">
                See how every scene scored
              </Link>
            </section>
          )}
        </div>
      </div>
      <PencilNote className="page-footnote">{stats.scenes ? "read it top to bottom, it all comes from the script" : ""}</PencilNote>
      <p className="kicker" style={{ padding: "0 4px" }}>
        {stats.scenes ? `${stats.scenes} scenes, ${hoursText(stats.hours)} on set.` : ""}
      </p>
    </>
  );
}
