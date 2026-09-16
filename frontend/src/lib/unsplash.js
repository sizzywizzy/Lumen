// Photos served from Unsplash's image CDN, which crops and resizes on request.
// Each photo asks for the width it is shown at and twice that for sharp
// screens, plus a small face-centred square for avatars. Everything served
// this way is free to use under the Unsplash License
// (https://unsplash.com/license).

const cdn = (id, width, extra = "") => `https://images.unsplash.com/${id}?auto=format&fit=crop&q=70&w=${width}${extra}`;

export function unsplash(id, width, details = {}) {
  return {
    src: cdn(id, width),
    srcSet: `${cdn(id, width)} ${width}w, ${cdn(id, width * 2)} ${width * 2}w`,
    thumb: cdn(id, 120, "&h=120&crop=faces"),
    ...details,
  };
}
