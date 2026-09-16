// Scroll reveal for every page: a block that starts below the fold waits out
// of sight and rises into focus the first time it scrolls into view (the CSS
// is [data-reveal] in index.css). One observer covers the whole app, including
// pages and tabs that mount later. Blocks already on screen when they mount
// are left alone, so nothing blinks on load, and nothing moves at all for
// people who ask for reduced motion.
//
// It works through data attributes and a custom property rather than
// classes, because React rewrites className on re-render but leaves
// attributes it does not manage alone.

const TARGETS = [
  ".section-head", ".step", ".example-panel", ".cta-band", ".craft-head", ".craft-card",
  ".card", ".agenda-day", ".quote", ".cast-role", ".actor-card",
].join(", ");

const NO_MOTION = "(prefers-reduced-motion: reduce)";
const TALL = 900; // taller than this, a block rises without the blur
const IN_VIEW = 0.94; // matches the observer's bottom margin below

export function installScrollReveal(root = document.body) {
  if (typeof IntersectionObserver === "undefined" || typeof MutationObserver === "undefined") return;
  const reduced = window.matchMedia(NO_MOTION);
  const pending = new Set();

  function settle(el) {
    delete el.dataset.reveal;
    delete el.dataset.revealLarge;
    el.style.removeProperty("--reveal-delay");
  }

  function reveal(el, order) {
    pending.delete(el);
    observer.unobserve(el);
    // inside a block that is itself rising: travel with it, not on its own
    if (el.parentElement?.closest("[data-reveal]")) {
      settle(el);
      return;
    }
    // blocks entering together follow one another
    el.style.setProperty("--reveal-delay", `${Math.min(order, 3) * 90}ms`);
    el.dataset.reveal = "shown";
    const done = (event) => {
      if (event.target !== el) return;
      el.removeEventListener("animationend", done);
      settle(el);
    };
    el.addEventListener("animationend", done);
    setTimeout(() => el.dataset.reveal === "shown" && settle(el), 2000); // if the animation never runs
  }

  const observer = new IntersectionObserver(
    (entries) => {
      let order = 0;
      for (const entry of entries) {
        if (entry.isIntersecting && pending.has(entry.target)) reveal(entry.target, order++);
      }
    },
    { rootMargin: "0px 0px -6% 0px" }
  );

  // A fast fling can carry a short block past the viewport between two
  // intersection checks. Once scrolling pauses, anything still waiting that
  // is on screen rises now, and anything already scrolled past simply shows.
  let sweepTimer = 0;
  function sweep() {
    let order = 0;
    for (const el of pending) {
      if (!el.isConnected) {
        pending.delete(el);
        observer.unobserve(el);
        continue;
      }
      const rect = el.getBoundingClientRect();
      if (rect.bottom <= 0) {
        pending.delete(el);
        observer.unobserve(el);
        settle(el);
      } else if (rect.top < window.innerHeight * IN_VIEW) {
        reveal(el, order++);
      }
    }
  }
  window.addEventListener(
    "scroll",
    () => {
      if (!pending.size) return;
      clearTimeout(sweepTimer);
      sweepTimer = setTimeout(sweep, 140);
    },
    { passive: true, capture: true }
  );

  function consider(el) {
    if (el.dataset.reveal || reduced.matches) return;
    const rect = el.getBoundingClientRect();
    if (!rect.height || rect.top < window.innerHeight) return; // not laid out, or already on screen
    if (rect.height > TALL) el.dataset.revealLarge = "";
    el.dataset.reveal = "pending";
    pending.add(el);
    observer.observe(el);
  }

  function scan(node) {
    if (!(node instanceof Element)) return;
    if (node.matches(TARGETS)) consider(node);
    node.querySelectorAll(TARGETS).forEach(consider);
  }

  scan(root);
  new MutationObserver((records) => {
    for (const record of records) record.addedNodes.forEach(scan);
  }).observe(root, { childList: true, subtree: true });
}
