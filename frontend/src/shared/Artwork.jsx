import Icon from "./Icon.jsx";
import { cn, initials } from "../lib/utils.js";

// Generated artwork for places where a photo belongs but none exists yet: a
// film-frame tile for every location on the schedule and a title-card poster
// for the production. Each takes a real image when one is available (a venue
// photo, a still, the actual poster) and paints its own art otherwise, so the
// pages never show an empty grey box.

// A palette per kind of place. Keyed by the words that turn up in the
// backend's location_type (city_street_night, warehouse_interior, ...) and in
// venue names; anything unknown gets a colour from its own name.
const ART = [
  { match: /street|city|alley|neon|downtown|district/, icon: "location_city", a: "#141f45", b: "#5b2a86", c: "#ff4fa3" },
  { match: /warehouse|factory|industrial|garage|hangar/, icon: "warehouse", a: "#2a1a12", b: "#6d3a1c", c: "#ff9a3c" },
  { match: /rooftop|roof|bar|lounge|club|nightlife|skyline/, icon: "nightlife", a: "#2a1030", b: "#7a1f5c", c: "#ffb347" },
  { match: /dock|harbor|harbour|pier|port|marina|boat|sea|ocean|beach/, icon: "anchor", a: "#0f2f3a", b: "#1f6f7a", c: "#ffd27a" },
  { match: /cab|car|taxi|vehicle|rig|trailer|road|highway|bus|train|station/, icon: "directions_car", a: "#3a2a0a", b: "#8a5a12", c: "#ffd45c" },
  { match: /apartment|flat|house|home|bedroom|kitchen|living/, icon: "home", a: "#2b2018", b: "#5c4632", c: "#f6a121" },
  { match: /office|corporate|lobby|boardroom|tower/, icon: "apartment", a: "#1b2430", b: "#3d5266", c: "#9dd5ff" },
  { match: /park|forest|wood|field|garden|farm|mountain|desert|lake/, icon: "park", a: "#14301f", b: "#2f6b3a", c: "#c9f27a" },
  { match: /diner|restaurant|cafe|coffee|kitchen/, icon: "restaurant", a: "#3a1a12", b: "#8a3c22", c: "#ffc87a" },
  { match: /hospital|clinic|lab|morgue/, icon: "local_hospital", a: "#1c2a2e", b: "#3b6b73", c: "#bff3ff" },
  { match: /school|campus|university|library/, icon: "school", a: "#2a2214", b: "#6a5623", c: "#ffe08a" },
  { match: /hotel|motel/, icon: "hotel", a: "#2a1424", b: "#6a2d5c", c: "#ffa6d6" },
  { match: /church|chapel|cathedral|temple/, icon: "church", a: "#1f1a2a", b: "#4b3f6b", c: "#ffe6a8" },
  { match: /stage|studio|theater|theatre|set/, icon: "theaters", a: "#231313", b: "#6a1f1f", c: "#ffb36b" },
];
const FALLBACK = [
  { icon: "movie", a: "#1c1b1f", b: "#3a3540", c: "#fac33d" },
  { icon: "movie", a: "#1a2230", b: "#334a63", c: "#8fd3ff" },
  { icon: "movie", a: "#2a1a1a", b: "#5a2f2f", c: "#ff9c7a" },
  { icon: "movie", a: "#1a2a22", b: "#2f5a48", c: "#a8f0c6" },
];

function hash(text) {
  let h = 0;
  for (const ch of String(text)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return h;
}

export function artFor(...hints) {
  const text = hints.filter(Boolean).join(" ").toLowerCase().replace(/_/g, " ");
  const found = ART.find((art) => art.match.test(text));
  return found || FALLBACK[hash(text) % FALLBACK.length];
}

// A small film frame for a location: sprocket holes down both edges, the
// place's colours behind an icon, or the photo when there is one.
export function LocationArt({ type, venue, image, size = "md", className }) {
  const art = artFor(type, venue);
  return (
    <span
      className={cn("loc-art", `loc-art--${size}`, className)}
      style={{ "--art-a": art.a, "--art-b": art.b, "--art-c": art.c }}
      aria-hidden="true"
    >
      {image ? <img src={image} alt="" loading="lazy" /> : <Icon name={art.icon} />}
    </span>
  );
}

// A portrait sitting in for a headshot nobody has sent yet: a head and
// shoulders lit from one side, in a colour taken from the actor's name, with
// their initials. Honest about being a placeholder, never someone else's face.
export function PortraitArt({ name, decorative = false, className }) {
  const art = FALLBACK[hash(name) % FALLBACK.length];
  return (
    <span
      className={cn("portrait-art", className)}
      style={{ "--art-a": art.a, "--art-b": art.b, "--art-c": art.c }}
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": `No headshot of ${name} yet` })}
    >
      <svg viewBox="0 0 100 125" preserveAspectRatio="xMidYMax slice" aria-hidden="true" focusable="false">
        <circle cx="50" cy="52" r="19" />
        <path d="M12 125c1-26 17-45 38-45s37 19 38 45z" />
      </svg>
      <span className="portrait-art__initials">{initials(name)}</span>
    </span>
  );
}

// Genre sets the poster's light: noir goes blue and magenta, horror red, and
// so on. The title is set in the logo's serif over the camera's beam.
const GENRE_LIGHT = [
  { match: /noir|thriller|crime|mystery|heist/, a: "#0e1633", b: "#4a1f6e", c: "#ff4fa3" },
  { match: /horror|slasher|ghost|haunt/, a: "#160707", b: "#5a0f12", c: "#ff5a3c" },
  { match: /sci-?fi|space|cyber|future|robot/, a: "#07131f", b: "#0f4a5c", c: "#7ff2ff" },
  { match: /romance|rom-?com|love/, a: "#2a0f1e", b: "#7a2a4c", c: "#ffb3c7" },
  { match: /comedy|satire|family|animated/, a: "#2a1c05", b: "#8a5a12", c: "#ffe680" },
  { match: /western|frontier|desert/, a: "#2a1a0c", b: "#7a4a1c", c: "#ffc76b" },
  { match: /fantasy|myth|magic|epic/, a: "#101a2e", b: "#3a2c6e", c: "#c7a8ff" },
  { match: /drama|indie|coming.of.age/, a: "#1c140c", b: "#5c4632", c: "#f6a121" },
  { match: /documentary|doc/, a: "#141a18", b: "#2f4a44", c: "#a8e6d2" },
  { match: /action|war|adventure|spy/, a: "#1a0f0a", b: "#6a2f14", c: "#ff9a3c" },
];

// A portrait title card for the production. Pass `image` for the real poster
// once one exists; until then the card paints its own key art. Either way the
// title (and, on the larger sizes, the tagline) is set over the art here, since
// the poster art carries no lettering of its own. `busy` shows the poster
// developing while a new one is made.
export function PosterCard({ title, genre, image, tagline, description, busy = false, size = "md", className }) {
  const text = String(genre || "").toLowerCase();
  const light = GENRE_LIGHT.find((g) => g.match.test(text)) || { a: "#1c1b1f", b: "#3a3540", c: "#fac33d" };
  const words = String(title || "Untitled").trim();
  return (
    <div
      className={cn("poster", `poster--${size}`, image && "poster--photo", busy && "is-painting", className)}
      style={{ "--art-a": light.a, "--art-b": light.b, "--art-c": light.c }}
      role="img"
      aria-label={description ? `${words} poster: ${description}` : `${words} poster`}
    >
      {/* keyed by the image, so each new poster fades in rather than swapping in place */}
      {image ? <img key={image} src={image} alt="" /> : <span className="poster__beam" aria-hidden="true" />}
      {tagline && <span className="poster__tagline">{tagline}</span>}
      <span className="poster__title">{words}</span>
      <span className="poster__caption">{genre ? genre : "A Lumen production"}</span>
      {busy && <span className="poster__develop" aria-hidden="true" />}
    </div>
  );
}
