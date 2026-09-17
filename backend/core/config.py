"""Central configuration. Reads env vars (.env locally, the host's env settings when deployed).

Every external key is optional: with no keys set, the whole pipeline runs on
mock data so anyone can develop and demo without credentials.

What is read, and what for. Every service here has a free plan, and Lumen
uses nothing beyond it:
  - Gemini (GEMINI_API_KEY): all agent reasoning, as JSON from Flash models on
    the free tier. No Google Search grounding, image generation or Vertex AI.
  - Supabase (SUPABASE_URL/KEY): accounts, pipeline state, simulations, runs.
  - Tavily (TAVILY_API_KEY): the talent scout's web search and the
    cultural-research step.
  - TMDb (TMDB_API_KEY): photos and credits for scouted actors, and the actor
    knowledge base's import.
  - PostgreSQL (DATABASE_URL, e.g. Supabase's own): the actor knowledge base.
"""
import os
from pathlib import Path


def _env_value(raw: str) -> str:
    """A .env value without its surrounding whitespace or matching quotes."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


# Load a local .env if present (no python-dotenv dependency needed).
_env_file = Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), _env_value(value))

BACKEND_DIR = Path(__file__).resolve().parents[1]
MOCK_DATA_DIR = BACKEND_DIR / "mock_data"
# Fallback persistence when Supabase is not configured. LUMEN_STATE_DIR points a
# second local server (a demo, a screenshot run) at its own folder.
LOCAL_STATE_DIR = Path(os.environ.get("LUMEN_STATE_DIR") or (BACKEND_DIR / ".state"))

# Agent skills: skills/<name>/SKILL.md at the repo root, next to backend/.
# LUMEN_SKILLS_DIR overrides it for containers that copy the folder elsewhere.
SKILLS_DIR = Path(os.environ.get("LUMEN_SKILLS_DIR") or (BACKEND_DIR.parent / "skills"))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# Where shared state lives:
#   auto     - Supabase when URL+KEY are set and the client is installed, else local JSON
#   supabase - require Supabase; fail loudly rather than silently using local files
#   local    - always local JSON, even with credentials present
# Hosted filesystems (Render's included) do not survive a redeploy, so
# deployments must run on "auto" (with Supabase configured) or "supabase".
# "local" is for offline dev.
STATE_BACKEND = os.environ.get("LUMEN_STATE_BACKEND", "auto").strip().lower()

# Browser origins allowed to call the API. "*" suits local dev; a public deploy
# lists its frontend, e.g. LUMEN_CORS_ORIGINS=https://lumen.vercel.app. An empty
# value counts as unset, so a blank host setting never locks every origin out.
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in (os.environ.get("LUMEN_CORS_ORIGINS") or "*").split(",")
    if origin.strip()
]

# How many proxies in front of the API append to X-Forwarded-For (1 on Render).
# The sign-in rate limit keys on the client address those proxies report; 0
# uses the socket's peer address, which is right when nothing sits in front.
TRUSTED_PROXY_HOPS = max(0, int(os.environ.get("LUMEN_TRUSTED_PROXY_HOPS") or 0))

# The actor knowledge base's PostgreSQL (services/casting_kb/db.py). Nothing
# else reads it; Supabase stays the store for accounts and pipeline state.
DATABASE_URL = os.environ.get("DATABASE_URL", "")
TMDB_API_KEY = os.environ.get("TMDB_API_KEY", "")
TMDB_LANGUAGE = os.environ.get("TMDB_LANGUAGE", "en-US")
EMBEDDING_MODEL = os.environ.get(
    "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
)
EMBEDDING_DIMENSIONS = int(os.environ.get("EMBEDDING_DIMENSIONS", "384"))

# Model tiering (AGENT.md guardrails): Flash by default, Pro only for heavy reasoning.
# NOTE: the previous defaults (gemini-2.0-flash / gemini-2.0-pro) 404 on current
# API keys — Google retired them for new users. These are ids verified against a
# live key; both stay env-overridable.
GEMINI_FLASH_MODEL = os.environ.get("GEMINI_FLASH_MODEL", "gemini-3.6-flash")
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-3.6-flash")

# Tried in order when the configured model is unavailable (404 retired /
# 429 quota / 503 overloaded), so a run degrades instead of dying.
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash,gemini-3-flash-preview"
    ).split(",")
    if m.strip()
]

# Per-request timeout (ms) and bounded concurrency for batched agent work.
GEMINI_TIMEOUT_MS = int(os.environ.get("GEMINI_TIMEOUT_MS", "60000"))
# How much of an uploaded screenplay a single model read gets (profiler, scene
# breakdown, audience analysis). 120k characters covers a full feature script.
SCRIPT_ANALYSIS_MAX_CHARS = int(os.environ.get("SCRIPT_ANALYSIS_MAX_CHARS", "120000"))
GEMINI_MAX_CONCURRENCY = int(os.environ.get("GEMINI_MAX_CONCURRENCY", "3"))

# Guardrails
MAX_NEGOTIATION_ITERATIONS = 2  # never unbounded (AGENT.md Section 1)
MAX_ASSET_REGENERATIONS = 2     # agent_visual retry cap

# Budget-driven scale: the total budget entered at intake sets every cap below.
DEFAULT_BUDGET_USD = 250_000
CASTING_CAP_SHARE = 0.10    # max quote for a single role, as a share of the total budget
LOCATIONS_SHARE = 0.15      # share of the total budget available for venues
PERSONA_COUNT = 200         # synthetic viewers per screening (AGENT.md Phase V)


def has_gemini() -> bool:
    return bool(GEMINI_API_KEY)


def has_tavily() -> bool:
    return bool(TAVILY_API_KEY)


def has_tmdb() -> bool:
    return bool(TMDB_API_KEY)


_supabase_warned = False


def has_supabase() -> bool:
    """True only when Supabase is configured AND the client library is present.

    Credentials in .env without `pip install supabase` used to take every store
    down the Supabase branch and raise ModuleNotFoundError on the first read.
    Falling back to the local JSON store keeps the app running and says so once.
    """
    global _supabase_warned
    if STATE_BACKEND == "local":
        return False
    if not (SUPABASE_URL and SUPABASE_KEY):
        if STATE_BACKEND == "supabase":
            raise RuntimeError(
                "LUMEN_STATE_BACKEND=supabase but SUPABASE_URL/SUPABASE_KEY are not set."
            )
        return False
    try:
        import supabase  # noqa: F401
    except ImportError:
        if STATE_BACKEND == "supabase":
            raise RuntimeError(
                "LUMEN_STATE_BACKEND=supabase but the 'supabase' package is not installed. "
                "Run: pip install -r backend/requirements.txt"
            ) from None
        if not _supabase_warned:
            _supabase_warned = True
            print(
                "[lumen] SUPABASE_URL/KEY are set but the 'supabase' package is not "
                "installed - falling back to local JSON state under backend/.state/. "
                "Run: pip install supabase",
                flush=True,
            )
        return False
    return True


def has_database() -> bool:
    """Return whether the actor KB can use a PostgreSQL connection."""
    return bool(DATABASE_URL)
