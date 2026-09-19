"""Coercion helpers for model output.

A model's JSON mode returns the requested shape almost every time, and "almost"
is enough to turn a whole pipeline run into a 500 when an agent indexes the
payload directly. Phase agents run a live answer through these before using
it: a field that is missing or the wrong type falls back to the value the
offline mock would have given, so a malformed reply degrades to the demo
answer instead of crashing the run.

**These repairs are the shape errors, counted.** Sixty-five call sites across
the agents say what each field has to be, which makes this module the product's
own record of how often a live reply arrives in the wrong shape — the number a
schema is supposed to drive down. `watching()` counts them for a block of work,
the way `llm.recording()` counts calls, and `eval/structured` reads that count
to say whether enforcing a schema is worth the coupling. Nothing is counted
unless someone is watching, so the cost outside an experiment is one
`ContextVar` read per coercion.
"""
import math
import re
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Optional

_CODE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")

# The repairs counted for the block of work running now, or None when nobody
# asked. Batched agent work coerces from several threads, hence the lock.
_tally: ContextVar[Optional[dict[str, int]]] = ContextVar("llm_output_tally", default=None)
_tally_lock = threading.Lock()


@contextmanager
def watching() -> Iterator[dict[str, int]]:
    """Count the coercions inside the block.

    {checked, repaired, clamped, clipped}: how many fields were run through
    these helpers, how many fell back to their default because the model gave
    nothing usable, how many numbers were outside their range, and how many
    strings ran past their limit. The last three are the ways a reply can be
    valid JSON and still not the shape the agent asked for.
    """
    tally = {"checked": 0, "repaired": 0, "clamped": 0, "clipped": 0}
    token = _tally.set(tally)
    try:
        yield tally
    finally:
        _tally.reset(token)


def tally() -> Optional[dict[str, int]]:
    """The tally being kept now, for handing to a worker thread."""
    return _tally.get()


@contextmanager
def adopt(counting: Optional[dict[str, int]]) -> Iterator[None]:
    """Count into `counting` for this block. A thread starts with an empty
    context, so batched work adopts its caller's tally (services/llm.py)."""
    if counting is None:
        yield
        return
    token = _tally.set(counting)
    try:
        yield
    finally:
        _tally.reset(token)


def _checked(repaired: bool = False, *, clamped: bool = False, clipped: bool = False) -> None:
    counting = _tally.get()
    if counting is None:
        return
    with _tally_lock:
        counting["checked"] += 1
        counting["repaired"] += int(repaired)
        counting["clamped"] += int(clamped)
        counting["clipped"] += int(clipped)


def mapping(value: Any, default: Optional[dict] = None) -> dict:
    """`value` if it is a dict, else a copy of `default`."""
    if isinstance(value, dict):
        _checked()
        return value
    _checked(repaired=True)
    return dict(default or {})


def listing(value: Any, default: Optional[list] = None) -> list:
    """`value` if it is a list, else a copy of `default`."""
    if isinstance(value, list):
        _checked()
        return value
    _checked(repaired=True)
    return list(default or [])


def number(value: Any, default: float, low: Optional[float] = None, high: Optional[float] = None) -> float:
    """A finite float clamped to [low, high]; `default` when it is not a number."""
    if isinstance(value, bool):
        _checked(repaired=True)
        return float(default)
    try:
        out = float(value)
    except (TypeError, ValueError):
        _checked(repaired=True)
        return float(default)
    if math.isnan(out) or math.isinf(out):
        _checked(repaired=True)
        return float(default)
    given = out
    if low is not None:
        out = max(low, out)
    if high is not None:
        out = min(high, out)
    _checked(clamped=out != given)
    return out


def boolean(value: Any, default: bool = False) -> bool:
    """Real booleans, 0/1, and the usual yes/no spellings; `default` otherwise."""
    if isinstance(value, bool):
        _checked()
        return value
    if isinstance(value, (int, float)):
        _checked()
        return value != 0
    if isinstance(value, str):
        word = value.strip().lower()
        if word in ("true", "yes", "y", "1"):
            _checked()
            return True
        if word in ("false", "no", "n", "0", ""):
            _checked()
            return False
    _checked(repaired=True)
    return bool(default)


def text(value: Any, default: str = "", limit: Optional[int] = None) -> str:
    """A stripped string, clipped to `limit`; `default` when empty or not text-like."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        out = ""
    else:
        out = str(value).strip()
    fell_back = not out
    if fell_back:
        out = str(default or "")
    clipped = bool(limit) and len(out) > limit
    _checked(repaired=fell_back, clipped=clipped)
    return out[:limit] if limit else out


def words(value: Any) -> str:
    """A code such as EXPOSITION_OVERLOAD as plain words ("exposition
    overload"); anything already written as prose is returned as it is.

    Counted by the `text` call inside it, not again here: it is one field."""
    out = text(value)
    return out.replace("_", " ").lower() if _CODE.match(out) else out
