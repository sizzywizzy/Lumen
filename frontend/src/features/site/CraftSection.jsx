import { Photo } from "./artifacts.jsx";
import { DIRECTOR_STILL, GOLDEN_HOUR_CREW } from "./images.js";
import { CallSheet } from "./paperwork.jsx";

// "The Craft Before the Code": the homepage's turn from the hero to How it
// works. Three reels pinned to a production scrapbook honour how films have
// always been made (an instinct, a stack of paper, a crew racing the light)
// before the page cuts to what Lumen does about the paper. Styles in
// tactile.css.

const PHOTO_SIZES = "(max-width: 640px) 80vw, (max-width: 1040px) 40vw, 340px";

// An archival print held into the scrapbook by black photo corners.
function VisionPrint() {
  return (
    <div className="craft-print">
      <Photo photo={DIRECTOR_STILL} sizes={PHOTO_SIZES} />
      <span className="photo-corners" aria-hidden="true" />
    </div>
  );
}

// Three frames of 35mm: the golden-hour shot and the frames either side of it.
function GoldenHourStrip() {
  return (
    <div className="film-strip">
      <span className="film-strip__edge" aria-hidden="true">
        <span>&#9656; 23</span>
        <span>Safety film</span>
        <span>&#9656; 23A</span>
      </span>
      <div className="film-strip__frames">
        <Photo photo={GOLDEN_HOUR_CREW} sizes={PHOTO_SIZES} decorative className="film-strip__frame" />
        <Photo photo={GOLDEN_HOUR_CREW} sizes={PHOTO_SIZES} className="film-strip__frame" />
        <Photo photo={GOLDEN_HOUR_CREW} sizes={PHOTO_SIZES} decorative className="film-strip__frame" />
      </div>
    </div>
  );
}

const REELS = [
  {
    id: "vision",
    title: "The Vision",
    copy: "Every masterpiece begins with human instinct.",
    caption: DIRECTOR_STILL.credit,
    Media: VisionPrint,
  },
  {
    id: "chaos",
    title: "The Chaos",
    copy: "Great stories shouldn't get lost in production logistics.",
    caption: "Call sheet, shoot day 2. Revised twice before breakfast.",
    Media: CallSheet,
  },
  {
    id: "momentum",
    title: "The Momentum",
    copy: "Keep your crew focused on creating magic, not recalculating shoot days.",
    caption: GOLDEN_HOUR_CREW.credit,
    Media: GoldenHourStrip,
  },
];

export default function CraftSection() {
  return (
    <section className="craft" aria-labelledby="craft-title">
      <div className="craft-inner">
        <header className="craft-head">
          <p className="craft-kicker">A love letter to the set</p>
          <h2 id="craft-title">
            The Craft <em>Before</em> the Code
          </h2>
          <p className="craft-lede">
            Every film starts with instinct, survives on paperwork and finishes in a race against the light. Lumen takes
            the paperwork, so the craft stays human.
          </p>
        </header>

        <div className="craft-grid">
          {REELS.map(({ id, title, copy, caption, Media }, i) => (
            <article className={`craft-card craft-card--${id}`} key={id}>
              <span className="craft-card__paper" aria-hidden="true" />
              <figure className="craft-figure">
                <div className="craft-media">
                  <Media />
                </div>
                <figcaption className="craft-caption">
                  Fig. {i + 1}. {caption}
                </figcaption>
              </figure>
              <div className="craft-card__body">
                <p className="craft-card__reel">Reel {String(i + 1).padStart(2, "0")}</p>
                <h3 className="craft-card__title">{title}</h3>
                <p className="craft-card__copy">{copy}</p>
              </div>
            </article>
          ))}
        </div>

        <p className="craft-cut">Match cut to:</p>
      </div>
    </section>
  );
}
