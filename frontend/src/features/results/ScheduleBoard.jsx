import { Fragment, useMemo, useState } from "react";
import Icon from "../../shared/Icon.jsx";
import StatusBadge from "../../shared/StatusBadge.jsx";
import { LocationArt } from "../../shared/Artwork.jsx";
import { cn, initials } from "../../lib/utils.js";
import {
  calendarDays, castLookup, clockLabel, dayLabel, dayOfMonth, hoursText, sceneMoves, shootDays, weekdayShort,
} from "../../lib/production.js";

// The shoot, day by day: a strip of the whole shooting window on top (lit
// tiles are shoot days, click one to look at it alone), then each day as a
// call sheet — call times down the left, a film frame for the location, the
// scene with its slugline, who is in it, and anything the scheduler moved.

const CALL_TIME = 7; // every shoot day starts with a 7:00 AM call
const DAY_LENGTH = 10; // hours in a full day on set

const TIME_OF_DAY = {
  day: ["light_mode", "Day"],
  night: ["dark_mode", "Night"],
  dawn: ["wb_twilight", "Dawn"],
  dusk: ["wb_twilight", "Dusk"],
};

const MOVE_REASON = {
  venue_unavailable: "the venue wasn't free",
  cast_unavailable: "the cast wasn't free",
  past_wrap: "it fell after the wrap date",
};

const DAY_MS = 86400000;
const asDate = (iso) => new Date(`${iso}T12:00:00`);
const addDays = (iso, n) => {
  const d = new Date(asDate(iso).getTime() + n * DAY_MS);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const daysBetween = (a, b) => Math.round((asDate(b) - asDate(a)) / DAY_MS);

function WeekStrip({ days, selected, onSelect }) {
  const calendar = calendarDays(days); // rest days included, so the rhythm of the shoot shows
  const byDate = new Map(days.map((d) => [d.date, d]));
  return (
    <div className="week-strip" role="tablist" aria-label="Shoot days">
      <button
        type="button"
        role="tab"
        aria-selected={!selected}
        className={cn("week-day week-day--all", !selected && "is-selected")}
        onClick={() => onSelect(null)}
      >
        <span className="week-day__wd">Shoot</span>
        <span className="week-day__num">{days.length}</span>
        <span className="week-day__mark">{days.length === 1 ? "day" : "days"}</span>
      </button>
      {calendar.map((d) => {
        const day = byDate.get(d.date);
        const shoot = Boolean(day);
        const isSelected = selected === d.date;
        return (
          <button
            key={d.date}
            type="button"
            role="tab"
            aria-selected={isSelected}
            disabled={!shoot}
            className={cn("week-day", shoot ? "is-shoot" : "is-rest", isSelected && "is-selected")}
            onClick={() => onSelect(isSelected ? null : d.date)}
            title={shoot ? `${dayLabel(d.date)}: ${hoursText(day.hours)} on set` : `${dayLabel(d.date)}: rest day`}
          >
            <span className="week-day__wd">{weekdayShort(d.date)}</span>
            <span className="week-day__num">{dayOfMonth(d.date)}</span>
            <span className="week-day__mark">
              {shoot ? (
                <>
                  <Icon name="videocam" filled />
                  {day.hours}h
                </>
              ) : (
                <Icon name="bedtime" />
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function RestDays({ from, count }) {
  const first = addDays(from, 1);
  const last = addDays(from, count);
  return (
    <div className="agenda-rest">
      <Icon name="bedtime" />
      <span>{count === 1 ? `Rest day · ${dayLabel(first)}` : `${count} rest days · ${dayLabel(first)} – ${dayLabel(last)}`}</span>
    </div>
  );
}

function SceneRow({ scene, start, end, cast, move, compact }) {
  const tod = TIME_OF_DAY[scene.timeOfDay];
  // the character, and the actor playing them once casting has locked a pick
  const people = scene.roleIds.length
    ? scene.roleIds.map((id) => ({ id, ...(cast[id] || { role: id, actor: null }) }))
    : scene.cast.map((name) => ({ id: name, role: name, actor: null }));

  return (
    <li className="agenda-row" data-setting={scene.intExt || "INT"}>
      <div className="agenda-time">
        <strong>{clockLabel(start)}</strong>
        <span>to {clockLabel(end)}</span>
      </div>
      <LocationArt type={scene.locationType} venue={scene.venue} image={scene.image} size={compact ? "sm" : "md"} />
      <div className="agenda-main">
        <div className="agenda-title-row">
          {scene.number && <span className="scene-badge">Sc. {scene.number}</span>}
          <h4 className="agenda-title">{scene.name}</h4>
          <StatusBadge status={scene.status} />
        </div>
        {scene.heading && <div className="slugline">{scene.heading}</div>}
        {!compact && scene.summary && <p className="agenda-summary">{scene.summary}</p>}
        <div className="agenda-chips">
          {scene.venue && (
            <span className="chip">
              <Icon name="location_on" />
              {scene.venue}
            </span>
          )}
          {scene.setting && <span className="chip chip--setting">{scene.setting}</span>}
          {tod && (
            <span className="chip chip--plain">
              <Icon name={tod[0]} />
              {tod[1]}
            </span>
          )}
          <span className="chip chip--plain">
            <Icon name="schedule" />
            {hoursText(scene.hours)}
          </span>
          {move && (
            <span className="chip chip--moved" title={move.resolution}>
              <Icon name="event_repeat" />
              Moved from {dayLabel(move.wanted)}
              {MOVE_REASON[move.reason] ? `, ${MOVE_REASON[move.reason]}` : ""}
            </span>
          )}
        </div>
        {people.length > 0 && (
          <div className="agenda-cast">
            {people.map((p) => (
              <span
                className="cast-chip"
                key={p.id}
                title={p.actor ? `${p.actor.name} as ${p.role}` : `${p.role} (not cast yet)`}
              >
                <i className={cn("avatar-xs", p.actor && "is-cast")}>{p.actor ? p.actor.initials : initials(p.role)}</i>
                <span>
                  {p.role}
                  {p.actor && <em> · {p.actor.name}</em>}
                </span>
              </span>
            ))}
          </div>
        )}
        {scene.note && (
          <p className="agenda-note">
            <Icon name="sticky_note_2" />
            {scene.note}
          </p>
        )}
      </div>
    </li>
  );
}

function DayAgenda({ day, index, cast, moves, compact }) {
  let clock = CALL_TIME;
  const slots = day.scenes.map((scene) => {
    const start = clock;
    clock += scene.hours;
    return { scene, start, end: clock };
  });
  const venues = new Set(day.scenes.map((s) => s.venue).filter(Boolean)).size;
  const pct = Math.min(100, Math.round((day.hours / DAY_LENGTH) * 100));
  const over = day.hours > DAY_LENGTH;

  return (
    <section className="agenda-day" id={`day-${day.date}`}>
      <header className="agenda-day__head">
        <div>
          <span className="kicker">Day {index + 1}</span>
          <h3 className="agenda-day__date">{dayLabel(day.date)}</h3>
        </div>
        <div className="agenda-day__meta">
          <span className="chip chip--plain">
            <Icon name="movie" />
            {day.scenes.length} {day.scenes.length === 1 ? "scene" : "scenes"}
          </span>
          <span className="chip chip--plain">
            <Icon name="location_on" />
            {venues} {venues === 1 ? "location" : "locations"}
          </span>
          <div className={cn("hours-meter", over && "is-over")} title={`${hoursText(day.hours)} of a ${DAY_LENGTH}-hour day`}>
            <span className="hours-meter__label">
              <strong>{day.hours}h</strong> of a {DAY_LENGTH}-hour day
            </span>
            <span className="hours-meter__track">
              <i style={{ width: `${pct}%` }} />
            </span>
          </div>
        </div>
      </header>
      <ol className="agenda-list">
        {slots.map(({ scene, start, end }) => (
          <SceneRow key={scene.id} scene={scene} start={start} end={end} cast={cast} move={moves.get(scene.id)} compact={compact} />
        ))}
      </ol>
    </section>
  );
}

export default function ScheduleBoard({ state, compact = false }) {
  const days = useMemo(() => shootDays(state), [state]);
  const cast = useMemo(() => castLookup(state), [state]);
  const moves = useMemo(() => sceneMoves(state), [state]);
  const [selected, setSelected] = useState(null);

  if (!days.length) return <p className="card-note">No shoot days have been planned yet.</p>;
  const shown = selected ? days.filter((d) => d.date === selected) : days;

  return (
    <div className={cn("schedule-board", compact && "schedule-board--compact")}>
      <WeekStrip days={days} selected={selected} onSelect={setSelected} />
      {/* keyed on the selection so the list fades in when a day is picked */}
      <div className="agenda fade-in" key={selected || "all"}>
        {shown.map((day) => {
          const index = days.indexOf(day);
          const prev = index > 0 && !selected ? days[index - 1] : null;
          const gap = prev ? daysBetween(prev.date, day.date) - 1 : 0;
          return (
            <Fragment key={day.date}>
              {gap > 0 && <RestDays from={prev.date} count={gap} />}
              <DayAgenda day={day} index={index} cast={cast} moves={moves} compact={compact} />
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
