import { money } from "../../lib/utils.js";
import { dateRange } from "../../lib/production.js";
import { DayBars, Stat, ViewerBar } from "../results/parts.jsx";
import { PaperClip, Polaroid, Tape } from "./artifacts.jsx";
import { SAMPLE_HEADSHOT } from "./images.js";
import { ScriptPage } from "./paperwork.jsx";

// The homepage hero's picture of a plan, laid out like a production desk: the
// schedule taped over a marked-up script page, the top pick's casting
// Polaroid clipped to their card, and the test screening as a ticket stub.
// The numbers are the sample production's, read through the same helpers as
// the results pages. It is one labelled image to assistive technology.
export default function HeroCollage({ stats, lead, screen }) {
  const { pick } = lead;
  const label =
    `A sample plan from Lumen: ${stats.shootDays} shoot days and ${stats.hours} hours on set. ` +
    `The top pick for ${lead.name} is ${pick.name}, at ${money(pick.fee)} with a fit of ${pick.fit} out of 100. ` +
    `${screen.liked} of ${screen.viewers} test viewers liked the story.`;

  return (
    <div className="hero-visual hero-collage" role="img" aria-label={label}>
      <ScriptPage className="hero-script" />

      <div className="hero-card hero-card--schedule">
        <span className="slate-edge" />
        <Tape className="hero-tape" label="Wk 1" />
        <div className="card-head">
          <strong>Shoot schedule</strong>
          <span className="kicker">{dateRange(stats.first, stats.last)}</span>
        </div>
        <div className="stats hero-schedule__stats">
          <Stat value={stats.shootDays} label="Shoot days" />
          <Stat value={`${stats.hours}h`} label="On set" />
        </div>
        <DayBars days={stats.days} height={150} />
      </div>

      <div className="hero-card hero-card--pick">
        <Polaroid
          className="hero-polaroid"
          photo={pick.photo ? { ...SAMPLE_HEADSHOT, src: pick.photo, srcSet: undefined } : SAMPLE_HEADSHOT}
          caption={pick.name.split(" ")[0]}
        >
          <PaperClip />
        </Polaroid>
        <div className="tile-sub">Top pick for {lead.name}</div>
        <div className="tile-name">{pick.name}</div>
        <div className="tile-sub">
          {money(pick.fee)} · fit {pick.fit} of 100
        </div>
      </div>

      <div className="hero-card hero-card--score">
        <div className="ticket">
          <div className="ticket__main">
            <div className="ticket__kicker">Test screening</div>
            <div className="row row--tight ticket__score">
              <span className="stat-value">{screen.tomatometer}%</span>
              <span className="stat-label">Tomatometer</span>
            </div>
            <ViewerBar liked={screen.liked} viewers={screen.viewers} height={22} />
            <div className="stat-label ticket__foot">
              {screen.liked} of {screen.viewers} test viewers liked it
            </div>
          </div>
          <div className="ticket__stub">
            <span>Admit {screen.viewers}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
