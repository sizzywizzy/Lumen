"""The shooting window entered at intake: strict checks for the API, lenient reads
for the scheduler (older saved states may hold missing or odd values)."""
from datetime import date
from typing import Annotated, Optional

from pydantic import BeforeValidator

DEFAULT_START = date(2026, 9, 1)
MAX_WINDOW_DAYS = 366


def _blank_to_none(value):
    return None if value in ("", None) else value


# A YYYY-MM-DD date; an empty string means "not given".
IsoDate = Annotated[Optional[date], BeforeValidator(_blank_to_none)]


def window_problem(start: Optional[date], end: Optional[date]) -> Optional[str]:
    """A plain-language reason the window is unusable, or None."""
    if start and end:
        if end < start:
            return "The wrap date must be on or after the first shoot day."
        if (end - start).days > MAX_WINDOW_DAYS:
            return "The shooting window can be at most a year long."
    return None


def parse(value) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def settings_problem(settings: dict) -> Optional[str]:
    """Check a stored shoot_settings dict after new values were merged in."""
    return window_problem(parse((settings or {}).get("start_date")), parse((settings or {}).get("end_date")))


def read_window(settings: dict) -> tuple[date, Optional[date]]:
    """(first shoot day, planned wrap or None). A wrap before the start is ignored."""
    start = parse((settings or {}).get("start_date")) or DEFAULT_START
    end = parse((settings or {}).get("end_date"))
    return start, (end if end and end >= start else None)
