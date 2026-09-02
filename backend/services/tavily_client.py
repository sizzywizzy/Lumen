"""Optional web research for the cultural-sensitivity agent.

Classification rules, certification practice and recent controversies change
faster than any model's training data, so when a Tavily key is configured the
sensitivity pass is grounded in fetched sources and every claim carries its URL.

With no key this module reports `enabled = False` and the agent skips research
entirely — it never fabricates sources or pretends a lookup happened. Uses
urllib so the project gains no dependency.
"""
import json
import urllib.error
import urllib.request
from typing import Any

from core import config

ENDPOINT = "https://api.tavily.com/search"
TIMEOUT_S = 20


def enabled() -> bool:
    return config.has_tavily()


def search(query: str, *, max_results: int = 4) -> dict[str, Any]:
    """Return {"results": [{title, url, content}], "query": ...}.

    Never raises: a failed lookup degrades to an empty result set with an error
    note, so research problems cannot fail a whole simulation.
    """
    if not enabled():
        return {"query": query, "results": [], "skipped": "tavily_not_configured"}

    payload = json.dumps(
        {
            "api_key": config.TAVILY_API_KEY,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT, data=payload, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            body = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {"query": query, "results": [], "error": f"{type(exc).__name__}: {exc}"[:200]}

    return {
        "query": query,
        "results": [
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": (item.get("content") or "")[:600],
            }
            for item in body.get("results", [])[:max_results]
        ],
    }


def research_market(market_name: str, genre_hint: str = "") -> dict[str, Any]:
    """One focused lookup per release market."""
    query = (
        f"{market_name} film certification and censorship rules {genre_hint} "
        "content restrictions theatrical release"
    ).strip()
    return search(query)
