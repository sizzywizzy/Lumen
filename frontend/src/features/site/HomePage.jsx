import { useState } from "react";
import { Link } from "react-router-dom";
import BrandLogo from "../../shared/BrandLogo.jsx";
import Icon from "../../shared/Icon.jsx";
import { useAuth } from "../../shared/AuthContext.jsx";
import { cn, money } from "../../lib/utils.js";
import { castByRole, dateRange, scheduleStats, screening } from "../../lib/production.js";
import { SAMPLE_STATE } from "../../lib/sample.js";
import { DayBars, Quotes, RoleBlock, ScoreSummary, ShootDays, Stat, ViewerBar } from "../results/parts.jsx";

const STEPS = [
  ["Drop your script", "PDF, Final Draft, Fountain or plain text. Add your budget, your shooting dates and the city you're filming in."],
  ["Lumen does the legwork", "It breaks the script into scenes, books days and venues, looks for actors who fit each role, and runs a test screening."],
  ["You make the calls", "Confirm the top picks, adjust the schedule, and invite your crew to see the same plan."],
];
const TABS = [
  ["schedule", "Schedule"],
  ["cast", "Cast"],
  ["audience", "Audience"],
];

// The public homepage. Its example is Neon Nights, the built-in sample
// production, rendered with the same components as the real results pages.
export default function HomePage() {
  const { user } = useAuth();
  const [tab, setTab] = useState("schedule");
  const stats = scheduleStats(SAMPLE_STATE);
  const roles = castByRole(SAMPLE_STATE);
  const screen = screening(SAMPLE_STATE);
  const lead = roles[0];
  const startTo = user ? "/new" : "/register";

  return (
    <div className="home">
      <header className="home-header">
        <BrandLogo to="/" height={50} />
        <nav className="home-nav">
          <a href="#how" className="hide-small">How it works</a>
          <a href="#example" className="hide-small">Example</a>
          {user ? (
            <Link to="/overview" className="btn btn--primary">Open your dashboard</Link>
          ) : (
            <>
              <Link to="/login">Sign in</Link>
              <Link to="/register" className="btn btn--primary">Create a production</Link>
            </>
          )}
        </nav>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <h1>Drop in a script. Walk away with a shoot plan.</h1>
          <p className="hero-lede">
            Lumen reads your screenplay, lays out the shoot days, suggests the best actor for every role within your
            budget, and screens the story with 200 simulated viewers before a camera rolls.
          </p>
          <div className="hero-actions">
            <Link to={startTo} className="btn btn--primary btn--lg">
              <Icon name="upload" size={20} />
              Drop your script
            </Link>
            <a href="#example" className="btn btn--ghost btn--lg">See an example</a>
          </div>
          <p className="hero-note">Works with PDF, Final Draft, Fountain and plain text.</p>
        </div>

        <div className="hero-visual" aria-hidden="true">
          <div className="hero-card hero-card--schedule">
            <div className="card-head">
              <strong>Shoot schedule</strong>
              <span className="kicker">{dateRange(stats.first, stats.last)}</span>
            </div>
            <div className="stats" style={{ margin: "14px 0 20px", gap: "12px 28px" }}>
              <Stat value={stats.shootDays} label="Shoot days" />
              <Stat value={`${stats.hours}h`} label="On set" />
            </div>
            <DayBars days={stats.days} height={150} />
          </div>
          <div className="hero-card hero-card--pick">
            <div className="tile-sub">Top pick for {lead.name}</div>
            <div className="tile-person" style={{ marginTop: 14 }}>
              <span className="avatar-lg is-pick">{lead.pick.initials}</span>
              <div>
                <div className="tile-name">{lead.pick.name}</div>
                <div className="tile-sub">
                  {money(lead.pick.fee)} · fit {lead.pick.fit} of 100
                </div>
              </div>
            </div>
          </div>
          <div className="hero-card hero-card--score">
            <div className="row row--tight" style={{ alignItems: "baseline" }}>
              <span className="stat-value">{screen.tomatometer}%</span>
              <span className="stat-label">Tomatometer</span>
            </div>
            <div style={{ margin: "14px 0 12px" }}>
              <ViewerBar liked={screen.liked} viewers={screen.viewers} height={22} />
            </div>
            <div className="stat-label">
              {screen.liked} of {screen.viewers} test viewers liked it
            </div>
          </div>
        </div>
      </section>

      <div className="band">
        <section className="section" id="how">
          <div className="section-head">
            <h2>How it works</h2>
            <p>Three steps from a finished draft to a plan your whole team can work from.</p>
          </div>
          <div className="steps">
            {STEPS.map(([title, text], i) => (
              <div className="step" key={title}>
                <span className="step-number">{i + 1}</span>
                <h3>{title}</h3>
                <p>{text}</p>
              </div>
            ))}
          </div>
        </section>
      </div>

      <section className="section" id="example">
        <div className="section-head">
          <div>
            <h2>See it on a real script</h2>
            <p>
              Neon Nights, Lumen's sample production, is a neo-noir thriller about a cab-driving ex-detective chasing a
              deepfake blackmail ring. This is what Lumen made of it.
            </p>
          </div>
          <div className="pill-tabs" role="tablist">
            {TABS.map(([id, label]) => (
              <button
                key={id}
                type="button"
                role="tab"
                aria-selected={tab === id}
                className={cn("pill-tab", tab === id && "active")}
                onClick={() => setTab(id)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        <div className="example-panel">
          {tab === "schedule" && <ShootDays days={stats.days} />}
          {tab === "cast" && (
            <div className="example-cast">
              {roles.map((role) => (
                <RoleBlock key={role.roleId} role={role} />
              ))}
            </div>
          )}
          {tab === "audience" && (
            <div className="example-audience">
              <div>
                <ScoreSummary screen={screen} />
              </div>
              <div className="stack stack--sm">
                <div className="kicker">What the test audience said</div>
                <Quotes reviews={screen.reviews} />
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="section" style={{ paddingTop: 0 }}>
        <div className="cta-band">
          <div>
            <h2>Your next shoot starts with a script.</h2>
            <p>Create a production, drop in your draft, and invite your crew when you're ready.</p>
          </div>
          <Link to={startTo} className="btn btn--amber btn--lg">
            <Icon name="upload" size={20} />
            Drop your script
          </Link>
        </div>
      </section>

      <footer className="home-footer">
        <div className="row">
          <BrandLogo to="/" height={32} />
          <span>Production planning for film teams</span>
        </div>
        <nav>
          {user ? (
            <Link to="/overview">Your dashboard</Link>
          ) : (
            <>
              <Link to="/login">Sign in</Link>
              <Link to="/register">Create a production</Link>
            </>
          )}
        </nav>
      </footer>
    </div>
  );
}
