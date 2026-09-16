// Press feedback for every clickable control: the element dips under the
// pointer (CSS :active in index.css) and a ripple spreads out from the click
// point. One document-level listener covers the whole app, including controls
// that mount later. The ripple lives in its own clipped layer inside the
// control, so a button's hover halo, which sits outside its box, is never
// clipped along with it.

const TARGETS = [
  ".btn", ".nav-item", ".nav-tab", ".site-tab", ".tab", ".pill-tab", ".pill-toggle button",
  ".account-item", ".account-button", ".month-tile", ".tag-chip", ".status-pill--button",
  ".status-option", ".drop", ".dropzone", ".card-link", ".home-link",
  ".actor-card__print", ".profile-strip__frame", "button.credit__frame",
].join(", ");

const NO_MOTION = "(prefers-reduced-motion: reduce)";

function spawnRipple(target, x, y) {
  const rect = target.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  // twice the diagonal, so the wave still covers the far corner from any click point
  const size = Math.ceil(Math.hypot(rect.width, rect.height)) * 2;

  const host = document.createElement("span");
  host.className = "ripple-host";
  host.setAttribute("aria-hidden", "true");
  const wave = document.createElement("span");
  wave.className = "ripple";
  wave.style.width = `${size}px`;
  wave.style.height = `${size}px`;
  wave.style.left = `${x - rect.left - size / 2}px`;
  wave.style.top = `${y - rect.top - size / 2}px`;
  host.appendChild(wave);

  // Inline styles rather than classes: React rewrites className on re-render
  // (a NavLink turning active does exactly that mid-ripple) but leaves inline
  // properties it does not manage alone.
  const style = target.style;
  const previous = { position: style.position, isolation: style.isolation };
  if (getComputedStyle(target).position === "static") style.position = "relative";
  style.isolation = "isolate";
  target.appendChild(host);

  let finished = false;
  const done = () => {
    if (finished) return;
    finished = true;
    host.remove();
    if (!target.querySelector(":scope > .ripple-host")) {
      style.position = previous.position;
      style.isolation = previous.isolation;
    }
  };
  wave.addEventListener("animationend", done, { once: true });
  setTimeout(done, 800); // in case the animation never fires (hidden mid-way)
}

function findTarget(node) {
  if (!(node instanceof Element)) return null;
  const target = node.closest(TARGETS);
  if (!target || target.disabled || target.getAttribute("aria-disabled") === "true") return null;
  return target;
}

export function installPressEffects(root = document) {
  root.addEventListener(
    "pointerdown",
    (event) => {
      if (event.button !== 0) return;
      const target = findTarget(event.target);
      if (!target || window.matchMedia(NO_MOTION).matches) return;
      spawnRipple(target, event.clientX, event.clientY);
    },
    { passive: true }
  );
  // keyboard activation ripples from the centre
  root.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.repeat) return;
    const target = findTarget(event.target);
    if (!target || target !== event.target || window.matchMedia(NO_MOTION).matches) return;
    const rect = target.getBoundingClientRect();
    spawnRipple(target, rect.left + rect.width / 2, rect.top + rect.height / 2);
  });
}
