"""Coercion helpers for model output.

Gemini's JSON mode returns the requested shape almost every time, and "almost"
is enough to turn a whole pipeline run into a 500 when an agent indexes the
payload directly. Phase agents run a live answer through these before using
it: a field that is missing or the wrong type falls back to the value the
offline mock would have given, so a malformed reply degrades to the demo
answer instead of crashing the run.
"""
import math
import re
from typing import Any, Optional

_CODE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")


def mapping(value: Any, default: Optional[dict] = None) -> dict:
    """`value` if it is a dict, else a copy of `default`."""
    return value if isinstance(value, dict) else dict(default or {})


def listing(value: Any, default: Optional[list] = None) -> list:
    """`value` if it is a list, else a copy of `default`."""
    return value if isinstance(value, list) else list(default or [])


def number(value: Any, default: float, low: Optional[float] = None, high: Optional[float] = None) -> float:
    """A finite float clamped to [low, high]; `default` when it is not a number."""
    if isinstance(value, bool):
        return float(default)
    try:
        out = float(value)
    except (TypeError, ValueError):
        return float(default)
    if math.isnan(out) or math.isinf(out):
        return float(default)
    if low is not None:
        out = max(low, out)
    if high is not None:
        out = min(high, out)
    return out


def boolean(value: Any, default: bool = False) -> bool:
    """Real booleans, 0/1, and the usual yes/no spellings; `default` otherwise."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        word = value.strip().lower()
        if word in ("true", "yes", "y", "1"):
            return True
        if word in ("false", "no", "n", "0", ""):
            return False
    return bool(default)


def text(value: Any, default: str = "", limit: Optional[int] = None) -> str:
    """A stripped string, clipped to `limit`; `default` when empty or not text-like."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        out = ""
    else:
        out = str(value).strip()
    if not out:
        out = str(default or "")
    return out[:limit] if limit else out


def words(value: Any) -> str:
    """A code such as EXPOSITION_OVERLOAD as plain words ("exposition
    overload"); anything already written as prose is returned as it is."""
    out = text(value)
    return out.replace("_", " ").lower() if _CODE.match(out) else out
