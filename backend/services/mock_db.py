"""Loader for the mock databases in backend/mock_data/ (personas, venues, rules...)."""
import json
from functools import lru_cache
from typing import Any

from core import config


@lru_cache(maxsize=None)
def load(name: str) -> Any:
    """load("venues") -> parsed backend/mock_data/venues.json"""
    path = config.MOCK_DATA_DIR / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))
