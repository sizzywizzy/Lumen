"""agent_visual, key art: the poster for the screenplay dropped at intake.

Every poster draws its style at random from prompts.POSTER_STYLES, never the
style of the poster it replaces, so asking again gives a different take:

  agent_visual writes the concept (a tagline and a palette) with Flash
  -> agent_pr_risk vets it (verify_brand_safety); a blocked draft is redrafted,
     at most MAX_ASSET_REGENERATIONS times, then the offline concept stands in
  -> Lumen draws the art as an SVG in the style's motif and the concept's
     palette, with no lettering: the Overview sets the title and tagline over
     it, so the type is always spelled right and set in the site's own faces
  -> agent_visual broadcasts asset_status_update

No model paints anything: image generation is not in Gemini's free tier. With
no key, or when the model fails, the concept comes from the genre, and the
provenance says so.
"""
import base64
import math
import random
import re
from typing import Any, Optional

from core import config, llm_output
from core.auth.security import iso, new_id, now
from core.messaging.envelope import broadcast, log_event, make_envelope
from core.orchestrator.state import GlobalState
from domains.launch import prompts
from domains.launch.agents.phase6_marketing import pr_risk_check
from services import gemini_client

ASSET_ID = "AST_POSTER_KEYART"
SCRIPT_CHARS = 12_000  # the opening pages are plenty to art-direct from
W, H = 600, 900  # the art's canvas: 2:3, a one-sheet's proportions
_HEX = re.compile(r"#[0-9a-fA-F]{6}")


def pick_style(previous_key: str = "", rng: Optional[random.Random] = None) -> dict[str, str]:
    """A style at random, never the one the current poster already has."""
    pool = [style for style in prompts.POSTER_STYLES if style["key"] != previous_key]
    return (rng or random).choice(pool or list(prompts.POSTER_STYLES))


def _facts(state: GlobalState) -> dict[str, str]:
    """What the concept is drawn from: Phase I's reading of the screenplay and its opening pages."""
    context = state.script_context or {}
    return {
        "title": llm_output.text(context.get("title"), "Untitled", 160),
        "genre": llm_output.text(context.get("genre"), "", 120),
        "tone": llm_output.text(context.get("tone"), "", 160),
        "logline": llm_output.text(context.get("logline"), "", 400),
        "excerpt": llm_output.text(context.get("raw_text"), "", SCRIPT_CHARS),
        "fingerprint": llm_output.text(context.get("fingerprint"), "", 64),
    }


def _offline_concept(facts: dict[str, str]) -> dict[str, Any]:
    """The concept by genre alone: what an offline poster uses, and the fallback
    for a malformed or repeatedly blocked draft. Spoiler-free by construction."""
    genre = facts["genre"].lower()
    tagline, palette = next(
        ((line, colours) for words, line, colours in prompts.POSTER_GENRES if any(w in genre for w in words)),
        prompts.POSTER_DEFAULT,
    )
    return {"tagline": tagline, "palette": list(palette)}


def _palette(value: Any, default: list[str]) -> list[str]:
    colours = [str(c).strip() for c in llm_output.listing(value) if _HEX.fullmatch(str(c).strip())]
    return colours[:5] if len(colours) >= 3 else list(default)


def _concept_prompt(facts: dict[str, str], style: dict[str, str], blocked: list[str]) -> str:
    lines = [
        f"FILM: {facts['title']}",
        f"GENRE: {facts['genre'] or 'not stated'}",
        f"TONE: {facts['tone'] or 'not stated'}",
        f"LOGLINE: {facts['logline'] or 'not stated'}",
        f"STYLE: {style['label']}: {style['direction']}",
    ]
    if blocked:
        lines.append(f"PR review blocked your last draft for: {', '.join(blocked)}. Leave that out.")
    if facts["excerpt"]:
        lines.append(f"SCREENPLAY (opening {len(facts['excerpt']):,} characters):\n{facts['excerpt']}")
    return "\n".join(lines)


def _concept(state: GlobalState, facts: dict[str, str], style: dict[str, str]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Draft the concept and put it through agent_pr_risk, redrafting a blocked
    one. Returns (concept, trace)."""
    offline = _offline_concept(facts)
    blocked: list[str] = []
    for attempt in range(config.MAX_ASSET_REGENERATIONS):
        reply, trace = gemini_client.generate_json_traced(
            _concept_prompt(facts, style, blocked), system=prompts.POSTER_SYSTEM, mock=offline,
        )
        draft = llm_output.mapping(reply, offline)
        # Coerced field by field, so a malformed reply degrades to the offline concept.
        concept = {
            "tagline": llm_output.text(draft.get("tagline"), offline["tagline"], 120),
            "palette": _palette(draft.get("palette"), offline["palette"]),
        }
        request = log_event(state, make_envelope(
            "agent_visual", "agent_pr_risk", "verify_brand_safety",
            {"asset_id": ASSET_ID, "caption": concept["tagline"]},
        ))
        verdict = pr_risk_check(state, request)
        if verdict["status"] == "APPROVED":
            return concept, {**trace, "drafts": attempt + 1}
        blocked = verdict["reasons"]
        log_event(state, broadcast("agent_visual", "asset_status_update", {
            "asset_id": ASSET_ID, "status": "BLOCKED",
            "blocker_details": {"blocked_by_agent": "agent_pr_risk", "reasons": blocked,
                                "auto_retry": attempt + 1 < config.MAX_ASSET_REGENERATIONS},
        }))
    return offline, {"source": "mock", "model": None, "reason": "pr_blocked", "blocked": blocked}


# ------------------------------------------------------------------ the art --


def _rgb(colour: str) -> tuple[int, int, int]:
    return int(colour[1:3], 16), int(colour[3:5], 16), int(colour[5:7], 16)


def _mix(a: str, b: str, share: float) -> str:
    """Colour `a` moved `share` of the way towards `b`."""
    return "#" + "".join(f"{round(x + (y - x) * share):02x}" for x, y in zip(_rgb(a), _rgb(b)))


def _luma(colour: str) -> float:
    r, g, b = _rgb(colour)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _ridge(rng: random.Random, base: float, swing: float, fill: str) -> str:
    """A far range of hills: a jagged random walk along `base`."""
    y, points = base, []
    for x in range(-20, W + 41, 40):
        y = min(base + swing, max(base - swing * 3, y + rng.uniform(-swing, swing)))
        points.append(f"{x},{y:.0f}")
    return f'<path d="M-20,{H} L{" L".join(points)} L{W + 20},{H} Z" fill="{fill}"/>'


def _skyline(rng: random.Random, base: float, fill: str, light: str) -> list[str]:
    """A city block standing on `base`, with a few lit windows."""
    shapes, x = [], -10.0
    while x < W + 10:
        width, height = rng.uniform(28, 74), rng.uniform(50, 240)
        top = base - height
        shapes.append(f'<rect x="{x:.0f}" y="{top:.0f}" width="{width:.0f}" height="{H - top:.0f}" fill="{fill}"/>')
        for _ in range(rng.randint(0, 5)):
            wx, wy = x + rng.uniform(4, max(5, width - 8)), top + rng.uniform(8, max(9, height - 12))
            shapes.append(f'<rect x="{wx:.0f}" y="{wy:.0f}" width="3" height="5" fill="{light}" fill-opacity="0.75"/>')
        x += width + rng.uniform(0, 8)
    return shapes


def _figure(x: float, y: float, scale: float, ink: str) -> str:
    """A small standing figure in a long coat, feet at (x, y)."""
    return (
        f'<g transform="translate({x:.0f},{y:.0f}) scale({scale:.2f})" fill="{ink}">'
        '<circle cx="0" cy="-60" r="7.5"/>'
        '<path d="M-7,-52 Q0,-55 7,-52 L13,-10 L5,-10 L4,0 L1,0 L0,-8 L-1,0 L-4,0 L-5,-10 L-13,-10 Z"/>'
        "</g>"
    )


def sketch_svg(palette: list[str], motif: str, seed: int) -> bytes:
    """The poster art: a lone figure on a hill under a glowing sky, drawn in the
    style's motif and the concept's palette. No lettering, so the page sets the
    title and tagline over it."""
    rng = random.Random(seed)
    colours = sorted((c for c in palette if _HEX.fullmatch(c)), key=_luma)
    if len(colours) < 3:
        colours = sorted(prompts.POSTER_DEFAULT[1], key=_luma)
    ink, light = colours[0], colours[-1]
    sky, horizon = _mix(colours[1], ink, 0.35), _mix(colours[-2], light, 0.2)

    cx, cy = rng.uniform(170, 430), rng.uniform(230, 360)
    radius = rng.uniform(130, 175) if motif == "disc" else rng.uniform(62, 110)
    ground = rng.uniform(560, 620)  # where the far layers stand

    shapes = [f'<rect width="{W}" height="{H}" fill="url(#sky)"/>', f'<rect width="{W}" height="{H}" fill="url(#glow)"/>']
    if motif == "rays":
        for i in range(18):
            a = 2 * math.pi * i / 18
            b = a + math.pi / 36
            points = [(cx, cy), (cx + 1200 * math.cos(a), cy + 1200 * math.sin(a)),
                      (cx + 1200 * math.cos(b), cy + 1200 * math.sin(b))]
            coords = " ".join(f"{px:.0f},{py:.0f}" for px, py in points)
            shapes.append(f'<polygon points="{coords}" fill="{light}" fill-opacity="0.1"/>')
    shapes.append(f'<circle cx="{cx:.0f}" cy="{cy:.0f}" r="{radius:.0f}" fill="{light}"/>')
    if motif == "halftone":
        # the second ink printed a little off register, then the dot screen
        shapes.append(f'<circle cx="{cx + 14:.0f}" cy="{cy + 10:.0f}" r="{radius:.0f}" fill="none" '
                      f'stroke="{ink}" stroke-width="3" stroke-opacity="0.5"/>')
        shapes.append(f'<rect width="{W}" height="{ground:.0f}" fill="url(#dots)" opacity="0.3"/>')
    if motif == "skyline":
        shapes.extend(_skyline(rng, ground, _mix(horizon, ink, 0.55), light))
    elif motif != "disc":
        shapes.append(_ridge(rng, ground - 70, 26, _mix(horizon, ink, 0.4)))
        shapes.append(_ridge(rng, ground, 20, _mix(horizon, ink, 0.7)))

    # The hill in the foreground, a curve through its crest, and the figure standing on it.
    left, crest, right = rng.uniform(700, 760), rng.uniform(610, 680), rng.uniform(700, 780)
    control = 2 * crest - (left + right) / 2
    shapes.append(f'<path d="M-20,{H} L-20,{left:.0f} Q300,{control:.0f} 620,{right:.0f} L620,{H} Z" fill="{ink}"/>')
    t = rng.uniform(0.32, 0.68)
    fx = (1 - t) ** 2 * -20 + 2 * (1 - t) * t * 300 + t ** 2 * 620
    fy = (1 - t) ** 2 * left + 2 * (1 - t) * t * control + t ** 2 * right
    shapes.append(_figure(fx, fy + 2, rng.uniform(0.9, 1.25), ink))
    shapes.append(f'<rect width="{W}" height="{H}" filter="url(#grain)"/>')
    shapes.append(f'<rect width="{W}" height="{H}" fill="url(#vignette)"/>')

    defs = (
        "<defs>"
        f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{sky}"/>'
        f'<stop offset="0.62" stop-color="{horizon}"/><stop offset="1" stop-color="{ink}"/></linearGradient>'
        f'<radialGradient id="glow" cx="{cx:.0f}" cy="{cy:.0f}" r="{radius * 3.4:.0f}" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{light}" stop-opacity="0.6"/><stop offset="1" stop-color="{light}" stop-opacity="0"/>'
        "</radialGradient>"
        '<radialGradient id="vignette" cx="0.5" cy="0.42" r="0.78"><stop offset="0.6" stop-color="#000" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#000" stop-opacity="0.55"/></radialGradient>'
        '<pattern id="dots" width="11" height="11" patternUnits="userSpaceOnUse" patternTransform="rotate(21)">'
        f'<circle cx="5.5" cy="5.5" r="2.3" fill="{light}"/></pattern>'
        '<filter id="grain"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch"/>'
        '<feColorMatrix values="0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.1 0"/></filter>'
        "</defs>"
    )
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}">{defs}{"".join(shapes)}</svg>'
    return svg.encode("utf-8")


# --------------------------------------------------------------- the poster --


def paint(
    state: GlobalState,
    *,
    previous_style: str = "",
    started_by: Optional[str] = None,
    rng: Optional[random.Random] = None,
) -> dict[str, Any]:
    """Make one poster for the state's screenplay and return its record for
    services/poster_store.py. The A2A traffic is appended to state.event_log."""
    rng = rng or random.Random()
    style = pick_style(previous_style, rng)
    facts = _facts(state)
    concept, concept_trace = _concept(state, facts, style)
    art = sketch_svg(concept["palette"], style["sketch"], rng.randrange(2**31))
    concept = {**concept, "alt_text": f"{style['label']} art for {facts['title']}: "
                                      "a lone figure on a hill under a glowing sky."}

    poster_id = new_id("PST").upper()
    log_event(state, broadcast("agent_visual", "asset_status_update", {
        "asset_id": ASSET_ID, "type": "poster", "status": "APPROVED", "poster_id": poster_id,
        "style": style["label"], "concept_by": concept_trace.get("model") or "offline",
    }))
    return {
        "project_id": state.project_id,
        "poster_id": poster_id,
        "created_at": iso(now()),
        "started_by": started_by,
        "script_fingerprint": facts["fingerprint"],
        "title": facts["title"],
        "style": {"key": style["key"], "label": style["label"]},
        "concept": concept,
        "provenance": {"concept": concept_trace},
        "image_mime": "image/svg+xml",
        "image_base64": base64.b64encode(art).decode("ascii"),
    }
