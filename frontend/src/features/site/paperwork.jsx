import { cn } from "../../lib/utils.js";
import { CoffeeRing, PencilNote } from "./artifacts.jsx";

// Paperwork from Neon Nights, the sample production, as it looks mid-shoot:
// a working copy of a script page and a marked-up call sheet. Scene numbers,
// sets and hours match the sample plan in lib/sample.js. Styles in tactile.css.

// A script page in Courier, three-hole punched with brass brads, the lead's
// first appearance highlighted and the director's pencil in the margins.
// Decorative: it sits inside the hero collage, which describes itself.
export function ScriptPage({ className }) {
  return (
    <div className={cn("script-page", className)} aria-hidden="true">
      <div className="paper-sheet script-page__under" />
      <div className="paper-sheet script-page__sheet">
        <span className="script-page__holes" />
        <p className="script-page__num">14.</p>
        <p className="script-page__slug">
          EXT. NEON DISTRICT STREET - <span className="pencil-ring">NIGHT</span>
        </p>
        <p className="script-page__action">
          <mark className="highlighter">MARA VOSS</mark> (30s), ex-detective, waits in a checker cab with the meter
          running. Rain needles the glass.
        </p>
        <p className="script-page__cue">MARA</p>
        <p className="script-page__line">You&rsquo;re late. And you&rsquo;re not the mayor.</p>
        <p className="script-page__cue">SILAS (O.S.)</p>
        <p className="script-page__line">Tonight I&rsquo;m whoever the footage says I am.</p>
        <p className="script-page__cue">MARA</p>
        <p className="script-page__line">Then the footage is about to get worse.</p>
        <PencilNote className="script-page__note script-page__note--rig">rain tower, 4 hrs</PencilNote>
        <PencilNote className="script-page__note script-page__note--cast">cast? Lucia &#10003;</PencilNote>
        <CoffeeRing className="script-page__coffee" />
      </div>
    </div>
  );
}

const CALL_ROWS = [
  { scene: 3, set: "INT. THE NEON LOUNGE", time: "N", hours: 6 },
  { scene: 4, set: "INT. SKYLINE ROOFTOP", time: "N", hours: 4 },
  { scene: 6, set: "EXT. EAST HARBOR DOCKS", time: "D", hours: 3, struck: true },
];

// A typed call sheet from a production binder, revised in red pencil: the
// dawn exterior struck and pushed to Sunday, a worried note about rain and a
// coffee ring from the 6 AM meeting.
export function CallSheet({ className }) {
  return (
    <div
      className={cn("call-sheet", className)}
      role="img"
      aria-label="A typed call sheet for shoot day 2, revised in red pencil: one scene struck out and moved to Sunday, a note asking about rain cover, and a coffee ring."
    >
      <span className="call-sheet__holes" aria-hidden="true" />
      <div className="call-sheet__head">
        <strong>Neon Nights</strong>
        <span>
          Call sheet <em className="call-sheet__rev">Rev. C</em>
        </span>
      </div>
      <div className="call-sheet__meta">
        <span>Thu, Sep 3</span>
        <span>Shoot day 2 of 3</span>
      </div>
      <div className="call-sheet__meta">
        <span>Crew call 6:30 AM</span>
        <span>Shooting 7:30 AM</span>
      </div>
      <div className="call-sheet__table">
        <div className="call-sheet__row call-sheet__row--head">
          <span>Sc.</span>
          <span>Set</span>
          <span>D/N</span>
          <span>Hrs</span>
        </div>
        {CALL_ROWS.map((row) => (
          <div className={cn("call-sheet__row", row.struck && "is-struck")} key={row.scene}>
            <span>{row.scene}</span>
            <span>{row.set}</span>
            <span>{row.time}</span>
            <span>{row.hours}</span>
          </div>
        ))}
      </div>
      <p className="call-sheet__cast">Cast: 1. Mara &nbsp;2. Silas</p>
      <p className="call-sheet__note">Company move 2 PM</p>
      <PencilNote className="call-sheet__pencil call-sheet__pencil--moved">&rarr; Sun 6?</PencilNote>
      <PencilNote className="call-sheet__pencil call-sheet__pencil--rain">rain cover??</PencilNote>
      <CoffeeRing className="call-sheet__coffee" />
    </div>
  );
}
