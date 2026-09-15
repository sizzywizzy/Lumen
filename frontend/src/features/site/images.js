// The photographs on the homepage, kept in one place so a placeholder can be
// swapped without touching the components. All are free to use under the
// Unsplash License (https://unsplash.com/license); the 1935 still is a
// public-domain Dorothea Lange photograph that The New York Public Library
// published there. They load from Unsplash's image CDN, which resizes on
// request, so each asks for the width it is shown at and twice that for sharp
// screens.

const cdn = (id, width) => `https://images.unsplash.com/${id}?auto=format&fit=crop&q=70&w=${width}`;

const photo = (id, width, details) => ({
  src: cdn(id, width),
  srcSet: `${cdn(id, width)} ${width}w, ${cdn(id, width * 2)} ${width * 2}w`,
  ...details,
});

// https://unsplash.com/photos/qAai1NZxqes
export const DIRECTOR_STILL = photo("photo-1579856663721-7e5b98ee47c2", 480, {
  width: 600,
  height: 606,
  alt: "Director Pare Lorentz and cinematographer Paul Ivano setting up a film camera on a hillside near Bakersfield, California, in 1935",
  credit: "Pare Lorentz and Paul Ivano, Bakersfield, 1935. Photograph by Dorothea Lange, NYPL.",
});

// https://unsplash.com/photos/p2IDT4qkB14 (Martijn Baudoin)
export const GOLDEN_HOUR_CREW = photo("photo-1568840850902-cbd1206575c3", 480, {
  width: 900,
  height: 600,
  alt: "Three crew members silhouetted beside a camera on a tripod as the sun sets over a grassy field",
  credit: "Waiting on the light. Photograph by Martijn Baudoin, Unsplash.",
});

// https://unsplash.com/photos/zrZUCPgKMHc (Khashayar Kouchpeydeh). Stands in
// for the sample production's top pick until the data carries a headshot.
export const SAMPLE_HEADSHOT = photo("photo-1616840420121-7ad8ed885f11", 140, {
  width: 600,
  height: 600,
  alt: "Black-and-white headshot of an actor",
});
