import { unsplash } from "./unsplash.js";

// Everything the Cast page can say about an actor beyond fee and fit: photos,
// previous work and the characters played, training and background, and what
// the scout and the audition wrote. Candidate metadata is free-form, so each
// field is read under the few names it tends to arrive as, only http(s) links
// are kept, and anything missing is simply left out.
//
// The offline scout (no API keys) always proposes the same five fictional
// actors, who are also the homepage's sample cast. They carry a small demo
// profile below (placeholder photos from Unsplash, invented credits) so the
// page can be seen at its fullest in a demo. Actors found by the live scout
// never borrow from it: they show their own photos and credits, or a drawn
// portrait until there is one.

const text = (value) => (typeof value === "string" ? value.trim() : "");
const list = (value) => (Array.isArray(value) ? value : value ? [value] : []);
// a line of background from a string, or from an object's words ({ school, degree })
const line = (value) =>
  typeof value === "object" && value
    ? Object.values(value).map(text).filter(Boolean).join(", ")
    : text(value);

function firstOf(meta, keys) {
  for (const key of keys) {
    const value = meta?.[key];
    if (value != null && value !== "" && !(Array.isArray(value) && !value.length)) return value;
  }
  return undefined;
}

function webLink(value) {
  try {
    const url = new URL(String(value));
    if (!/^https?:$/.test(url.protocol) || /\.(internal|local)$/.test(url.hostname)) return null;
    return url.href;
  } catch {
    return null;
  }
}

function toPhoto(item, name, index) {
  const src = webLink(typeof item === "string" ? item : item?.url || item?.src || item?.image_url);
  if (!src) return null;
  const caption = text(item?.caption);
  return { src, thumb: src, alt: text(item?.alt) || caption || `${name}, photo ${index + 1}`, caption };
}

function toCredit(item, name) {
  if (typeof item === "string") return item.trim() ? { title: item.trim(), role: "", year: "", kind: "", image: null } : null;
  const title = text(item?.title || item?.project || item?.production);
  if (!title) return null;
  return {
    title,
    role: text(item.role || item.character || item.part),
    year: item.year ? String(item.year) : "",
    kind: text(item.kind || item.type || item.medium || item.format),
    image: item.image ? toPhoto(item.image, `${name} in ${title}`, 0) : null,
  };
}

// --------------------------------------------------------------- demo cast ---

// Placeholder photos, all free under the Unsplash License. Pages, in order of
// use: headshots zrZUCPgKMHc, 0fN7Fxv1eWA, ulTlfysiASI, 2pxka_hMvgM,
// Fn3NpmPVxUM; stills 5P9N_nE6PBs, ub77xN37pNs, p6rNTdAPbuk, oj0gsj-Zt_w,
// GWN0oUZwL5Y, l4UJSKwgkz8, PFfA3xlHFbQ, Hn3S90f6aak
// (https://unsplash.com/photos/<page>). The credits and schools are invented.
const still = (id, caption, alt) => unsplash(id, 640, { caption, alt, width: 640, height: 800 });

const DEMO_CAST = {
  "lucia morales": {
    headshot: unsplash("photo-1616840420121-7ad8ed885f11", 480, {
      width: 600, height: 600, position: "50% 30%", alt: "Headshot of Lucia Morales",
    }),
    photos: [
      still("photo-1770926062002-4d620b7dd17b", "Salt & Static (2025)", "Lucia Morales lit by neon through rain-streaked glass in a still from Salt & Static"),
      still("photo-1571173069043-82a7a13cee9f", "Low Tide Motel, on stage (2021)", "A lone performer under a warm spotlight on a bare stage in Low Tide Motel"),
    ],
    credits: [
      { title: "Salt & Static", year: "2025", kind: "Feature", role: "Detective Ana Ruiz", photo: 0 },
      { title: "The Long Fare", year: "2023", kind: "Short", role: "Rosa, a night-shift cabbie" },
      { title: "Low Tide Motel", year: "2021", kind: "Stage", role: "Marisol", photo: 1 },
    ],
    training: ["BFA in Acting, Westbrook Conservatory", "Stage combat and firearms safety"],
    followers: 85000,
    note: "Strong dramatic presence!",
  },
  "evelyn vance": {
    headshot: unsplash("photo-1506863530036-1efeddceb993", 480, {
      width: 600, height: 600, position: "50% 34%", alt: "Headshot of Evelyn Vance",
    }),
    photos: [
      still("photo-1503095396549-807759245b35", "Curtain call, The Quiet Season (2024)", "Performers silhouetted against a red curtain at the curtain call of The Quiet Season"),
    ],
    credits: [
      { title: "The Quiet Season", year: "2024", kind: "Stage", role: "Ingrid Hale", photo: 0 },
      { title: "County Line", year: "2022", kind: "Series, two episodes", role: "Dr. June Park" },
    ],
    training: ["MFA in Acting, Coastline School of Drama"],
    followers: 145000,
    note: "Great stillness on camera.",
  },
  "corinne bailey": {
    headshot: unsplash("photo-1642290687545-8ab7e6002472", 480, {
      width: 600, height: 600, position: "50% 30%", alt: "Headshot of Corinne Bailey",
    }),
    photos: [
      still("photo-1630050525402-06c617847d27", "Rehearsal, Harbor Light Theatre Company", "A company rehearsing on a bare stage under work lights at Harbor Light Theatre Company"),
    ],
    credits: [],
    training: ["Voice and movement, Lakeside Arts Academy", "Improvisation workshop, The Backroom Players"],
    experience: [
      "Four seasons of regional theater with Harbor Light Theatre Company",
      "Guest spots on two streaming dramas",
      "Wrote and performed a one-person show, Last Call at Mel's",
    ],
    followers: 48000,
    note: "Reads beautifully. First feature?",
  },
  "darius thorne": {
    headshot: unsplash("photo-1676439777386-d67cd2b32e7b", 480, {
      width: 600, height: 600, position: "50% 26%", alt: "Headshot of Darius Thorne",
    }),
    photos: [
      still("photo-1704461964028-697c2560de79", "Glass Harbor (2024)", "Darius Thorne silhouetted at a window over the city at night in a still from Glass Harbor"),
      still("photo-1728022038090-8ab88f8339bf", "Blocking a scene on set", "A crew blocking a scene around a camera on set, in black and white"),
    ],
    credits: [
      { title: "Glass Harbor", year: "2024", kind: "Feature", role: "Victor Crane", photo: 0 },
      { title: "Othello, Riverside Showcase", year: "2023", kind: "Stage", role: "Iago" },
    ],
    training: ["Stage combat, Southwest Actors Studio", "Screen acting intensive, Downtown Film Lab"],
    followers: 310000,
    note: "Charm first, menace second.",
  },
  "caleb sterling": {
    headshot: unsplash("photo-1617746652908-91e66c07499a", 480, {
      width: 600, height: 600, position: "50% 30%", alt: "Headshot of Caleb Sterling",
    }),
    photos: [
      still("photo-1585699324551-f6c309eedeca", "Opening night, Crown of Ash live", "A packed theater watching a lit stage on the opening night of Crown of Ash live"),
      still("photo-1515634928627-2a4e0dae3ddf", "On set, Midnight Ledger (2023)", "A clapperboard raised in front of the camera on the set of Midnight Ledger"),
    ],
    credits: [
      { title: "Crown of Ash", year: "2025", kind: "Series lead", role: "King Aldric", photo: 0 },
      { title: "Midnight Ledger", year: "2023", kind: "Feature", role: "Julian Marsh", photo: 1 },
    ],
    training: ["Classical training and three seasons of repertory theater"],
    followers: 1200000,
    note: "Worth it, but not at this budget.",
  },
};

function demoFor(candidate) {
  if (candidate?.metadata?.is_live_scouted === true) return null;
  return DEMO_CAST[String(candidate?.name || "").trim().toLowerCase()] || null;
}

// ------------------------------------------------------------------ profile ---

export function castProfile(candidate) {
  const meta = candidate?.metadata || {};
  const name = candidate?.name || "This actor";
  const demo = demoFor(candidate);

  const ownHeadshot = toPhoto(firstOf(meta, ["headshot_url", "photo_url", "headshot"]) || candidate?.headshot_url, name, 0);
  const headshot = ownHeadshot ? { ...ownHeadshot, alt: `Headshot of ${name}` } : demo?.headshot || null;

  const ownPhotos = list(firstOf(meta, ["photos", "gallery", "images", "stills"]))
    .map((item, i) => toPhoto(item, name, i + 1))
    .filter(Boolean);
  const extraPhotos = ownPhotos.length ? ownPhotos : demo?.photos || [];

  const ownCredits = list(firstOf(meta, ["credits", "filmography", "previous_work", "notable_roles", "roles_played"]))
    .map((item) => toCredit(item, name))
    .filter(Boolean);
  const credits = ownCredits.length
    ? ownCredits
    : (demo?.credits || []).map(({ photo, ...credit }) => ({ ...credit, image: photo != null ? demo.photos[photo] : null }));

  const lines = (keys, fallback) => {
    const own = list(firstOf(meta, keys)).map(line).filter(Boolean);
    return own.length ? own : fallback || [];
  };

  // the headshot leads the filmstrip, then every other photo once, in order
  const seen = new Set();
  const photos = [headshot, ...extraPhotos].filter((photo) => photo && !seen.has(photo.src) && seen.add(photo.src));

  return {
    headshot,
    photos,
    credits,
    training: lines(["training", "education", "schooling"], demo?.training),
    experience: lines(["experience", "background", "creative_experience", "bio"], demo?.experience),
    agency: text(meta.agency),
    press: text(meta.recent_press),
    match: text(meta.director_match),
    review: text(meta.qualitative_review),
    followers: meta.followers_estimated ? 0 : Number(meta.followers) || demo?.followers || 0,
    feeIsEstimate: meta.quote_is_estimate === true,
    reel: webLink(candidate?.media_url),
    note: text(meta.casting_note) || demo?.note || "",
    // how the scout found them, the page that names them, and a TMDb match
    foundVia: meta.is_live_scouted === true ? text(meta.scouted_via) : "",
    source: webLink(meta.source_url),
    tmdb: meta.tmdb_match === "name" ? webLink(meta.tmdb_url) : null,
  };
}

// The picture to show for a person from lib/production.js actor(), or null.
export function portraitFor(person) {
  return person?.profile?.headshot || null;
}
