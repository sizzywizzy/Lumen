"""Crash-safe JSON files for the local stores (used when Supabase is not configured).

Every local store rewrites a whole file per change. Writing in place leaves a
truncated file behind if the process dies mid-write, and lets a reader see half
a file, so each write goes to a uniquely named sibling and is renamed over the
target: the rename is atomic on POSIX and on Windows. Windows refuses to
replace a file that another handle has open, so the rename is retried for a
moment, and the stores hold their lock while reading as well as writing.
"""
import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

_REPLACE_ATTEMPTS = 6


def _replace(source: str, target: Path) -> None:
    for attempt in range(_REPLACE_ATTEMPTS):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            # Windows: a reader (or a virus scanner) has the target open.
            if attempt == _REPLACE_ATTEMPTS - 1:
                raise
            time.sleep(0.02 * (attempt + 1))


def write_text(path: Path, text: str) -> None:
    """Write `text` to `path` atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace(temp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise


def write_json(path: Path, data: Any, **dump_options: Any) -> None:
    """Serialise `data` and write it to `path` atomically."""
    write_text(path, json.dumps(data, **dump_options))


def read_json(path: Path, default: Any = None) -> Any:
    """The parsed file, or `default` when it does not exist."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return default
    return json.loads(text)
