import { unsplash } from "../../lib/unsplash.js";

// The photographs in the homepage's "Craft Before the Code" section, kept in
// one place so a placeholder can be swapped without touching the components.
// The 1935 still is a public-domain Dorothea Lange photograph that The New
// York Public Library published on Unsplash. (The hero's Polaroid is the
// sample top pick's headshot, from lib/castProfiles.js.)

// https://unsplash.com/photos/qAai1NZxqes
export const DIRECTOR_STILL = unsplash("photo-1579856663721-7e5b98ee47c2", 480, {
  width: 600,
  height: 606,
  alt: "Director Pare Lorentz and cinematographer Paul Ivano setting up a film camera on a hillside near Bakersfield, California, in 1935",
  credit: "Pare Lorentz and Paul Ivano, Bakersfield, 1935. Photograph by Dorothea Lange, NYPL.",
});

// https://unsplash.com/photos/p2IDT4qkB14 (Martijn Baudoin)
export const GOLDEN_HOUR_CREW = unsplash("photo-1568840850902-cbd1206575c3", 480, {
  width: 900,
  height: 600,
  alt: "Three crew members silhouetted beside a camera on a tripod as the sun sets over a grassy field",
  credit: "Waiting on the light. Photograph by Martijn Baudoin, Unsplash.",
});
