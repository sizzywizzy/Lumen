"""Plain-language names for scenes, shared by the schedule and the test screening.

A scene always carries its `scene_id` for joins; `describe` makes sure it also has
a screenplay heading, a short title a producer would recognise, and a summary.
"""
import re

_ID_LIKE = re.compile(r"^\s*SCN[\s_-]*\d+", re.IGNORECASE)


def _clean(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit].rstrip()


def describe(scene: dict) -> dict:
    """A copy of `scene` with `heading`, `title` and `summary` filled in."""
    out = dict(scene)
    setting = "EXT" if str(scene.get("int_ext", "")).upper().startswith("EXT") else "INT"
    location = str(scene.get("location_type") or "location").replace("_", " ").strip()
    heading = _clean(scene.get("heading"), 80) or f"{setting}. {location.upper()}"
    title = _clean(scene.get("title"), 60)
    if not title or _ID_LIKE.match(title) or title.upper() == heading.upper():
        number = re.search(r"(\d+)\s*$", str(scene.get("scene_id", "")))
        title = f"{location.capitalize()} (scene {int(number.group(1))})" if number else location.capitalize()
    out.update(heading=heading, title=title, summary=_clean(scene.get("summary"), 200))
    return out


def titles(scenes: list[dict]) -> dict[str, str]:
    """scene_id -> title for every scene in a breakdown."""
    return {s["scene_id"]: describe(s)["title"] for s in scenes if isinstance(s, dict) and s.get("scene_id")}
