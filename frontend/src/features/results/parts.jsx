import { Link } from "react-router-dom";
import Icon from "../../shared/Icon.jsx";
import { cn, money } from "../../lib/utils.js";
import { calendarDays, dayLabel, dayOfMonth, hoursText, weekdayShort } from "../../lib/production.js";

// Initials until the data carries a headshot (see actor() in lib/production.js).
const Avatar = ({ person, className }) => (
  <span className={className}>{person.photo ? <img src={person.photo} alt="" loading="lazy" /> : person.initials}</span>
);

// Building blocks shared by the results pages and the homepage example.

export function Card({ title, action, children, className }) {
  return (
    <section className={cn("card", className)}>
      {(title || action) && (
        <div className="card-head">
          {title && <h2 className="card-title">{title}</h2>}
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function CardLink({ to, children }) {
  return (
    <Link to={to} className="card-link">
      {children}
      <Icon name="arrow_forward" size={16} />
    </Link>
  );
}

export function Stat({ value, label, large = false }) {
  return (
    <div className={cn("stat", large && "stat--lg")}>
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

export function Legend({ items }) {
  return (
    <div className="legend-row">
      {items.map(([label, hatched]) => (
        <span key={label}>
          <i className={cn("legend-dot", hatched && "hatch")} style={hatched ? { background: undefined } : undefined} />
          {label}
        </span>
      ))}
    </div>
  );
}

// Hours on set per day, with the rest of a ten-hour day shown as free time.
export function DayBars({ days, height = 200 }) {
  const calendar = calendarDays(days);
  const top = Math.max(10, ...calendar.map((d) => d.hours));
  const px = height / top;
  return (
    <div className="day-bars">
      {calendar.map((d) => {
        const free = top - d.hours;
        return (
          <div className="day-bar" key={d.date} title={`${dayLabel(d.date)}: ${d.hours ? `${hoursText(d.hours)} on set` : "no shooting"}`}>
            <div className="day-bar__stack" style={{ height: height + 4 }}>
              {free > 0 && <div className="day-bar__free hatch" style={{ height: free * px }} />}
              {d.hours > 0 && <div className="day-bar__shoot" style={{ height: d.hours * px }} />}
            </div>
            <div className={cn("day-bar__label", d.hours > 0 && "is-shoot")}>
              {weekdayShort(d.date)}
              <br />
              {dayOfMonth(d.date)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// One block per five viewers: amber liked it, hatched didn't.
export function ViewerBar({ liked, viewers, height = 28 }) {
  const blocks = 40;
  const likedBlocks = Math.round((liked / viewers) * blocks);
  return (
    <div className="viewer-bar" role="img" aria-label={`${liked} of ${viewers} viewers liked it`}>
      {Array.from({ length: blocks }, (_, i) => (
        <span key={i} className={i < likedBlocks ? "liked" : "hatch"} style={{ height }} />
      ))}
    </div>
  );
}

export function FitMeter({ value }) {
  return (
    <span className="fit">
      Fit {value}
      <span className="fit-meter">
        <i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
      </span>
    </span>
  );
}

export function ActorTile({ role, person }) {
  return (
    <div className={cn("tile", person.ruledOut && "tile--out")}>
      <div className="tile-top">
        <span className="chip chip--plain">{role}</span>
        {person.isPick && <span className="chip chip--ink">Top pick</span>}
      </div>
      <div className="tile-person">
        <Avatar person={person} className={cn("avatar-lg", person.isPick && "is-pick")} />
        <div>
          <div className="tile-name">{person.name}</div>
          <div className="tile-sub">{person.ruledOut ? "Ruled out" : person.place}</div>
        </div>
      </div>
      {person.ruledOut ? (
        <p className="tile-sub">{person.reason}</p>
      ) : (
        <div className="tile-foot">
          <strong>{money(person.fee)}</strong>
          <FitMeter value={person.fit} />
        </div>
      )}
    </div>
  );
}

function PersonRow({ person, pick = false }) {
  if (person.ruledOut) {
    return (
      <div className="person person--out">
        <Avatar person={person} className="avatar-lg" />
        <div className="person-main">
          <div className="person-name">{person.name}</div>
          <div className="why">Ruled out. {person.reason}</div>
        </div>
      </div>
    );
  }
  return (
    <div className={cn("person", pick && "person--pick")}>
      <Avatar person={person} className="avatar-lg" />
      <div className="person-main">
        <div className="person-name">{person.name}</div>
        <div className="person-sub">
          {pick ? "Top pick" : "Runner-up"}
          {person.place ? ` · ${person.place}` : ""}
        </div>
      </div>
      <div className="person-side">
        <strong>{money(person.fee)}</strong>
        <small>Fit {person.fit} of 100</small>
      </div>
    </div>
  );
}

export function RoleBlock({ role, showWhy = false }) {
  return (
    <div className="role-block">
      <div className="kicker">{role.type || "Role"}</div>
      <div className="role-name">{role.name}</div>
      {role.description && <div className="why">{role.description}</div>}
      {role.pick && <PersonRow person={role.pick} pick />}
      {showWhy && role.pick?.why && <p className="why">{role.pick.why}</p>}
      {role.runnersUp.map((person) => (
        <PersonRow key={person.id} person={person} />
      ))}
      {role.ruledOut.map((person) => (
        <PersonRow key={person.id} person={person} />
      ))}
      {!role.pick && !role.runnersUp.length && !role.ruledOut.length && (
        <p className="why">No actors have been suggested for this role yet.</p>
      )}
    </div>
  );
}

export function ScoreSummary({ screen }) {
  return (
    <>
      <div className="stats">
        <Stat large value={`${screen.tomatometer}%`} label={screen.fresh ? "Tomatometer · fresh" : "Tomatometer · rotten"} />
        <Stat large value={`${screen.audienceScore}%`} label="Audience score" />
      </div>
      <div style={{ margin: "22px 0 14px" }}>
        <ViewerBar liked={screen.liked} viewers={screen.viewers} height={30} />
      </div>
      <Legend
        items={[
          [`Liked it · ${screen.liked} viewers`, false],
          [`Didn't · ${screen.notLiked} viewers`, true],
        ]}
      />
    </>
  );
}

export function Quotes({ reviews }) {
  return (
    <div className="quotes">
      {reviews.map((review, i) => (
        <div className="quote" key={`${review.source}-${i}`}>
          <p>“{review.quote}”</p>
          <small>
            {review.source}
            {review.score ? ` · ${review.score}` : ""}
          </small>
        </div>
      ))}
    </div>
  );
}

// Shown on every results page until the first script has been planned.
export function NoPlanYet({ canEdit }) {
  return (
    <section className="card empty-plan">
      <h2>Your plan will show up here</h2>
      <p>
        Drop in a script and Lumen will lay out the shoot days, suggest the best actor for every role and screen the
        story with 200 test viewers.
      </p>
      {canEdit ? (
        <Link to="/new" className="btn btn--primary btn--lg">
          <Icon name="upload" size={18} />
          Drop your script
        </Link>
      ) : (
        <p className="body-sm">Ask a producer on this production to drop in the script.</p>
      )}
    </section>
  );
}
