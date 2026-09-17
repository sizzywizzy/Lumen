"""Central configuration. Reads env vars (.env locally, the host's env settings when deployed).

Every external key is optional: with no keys set, the whole pipeline runs on
mock data so anyone can develop and demo without credentials.

What is read, and what for:
  - Gemini (GEMINI_API_KEY): all agent reasoning and the poster art. Vertex AI
    through gcloud credentials stands in only when GOOGLE_GENAI_USE_VERTEXAI
    and GOOGLE_CLOUD_PROJECT are set.
  - Supabase (SUPABASE_URL/KEY): accounts, pipeline state, simulations, runs.
  - Tavily (TAVILY_API_KEY): web research for the cultural-research step.
  - TMDb and PostgreSQL (TMDB_API_KEY, DATABASE_URL or the Cloud SQL
    settings): the actor knowledge base only.
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
# Hosted filesystems (Render, Cloud Run) do not survive a redeploy, so
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

# The actor knowledge base's PostgreSQL (services/casting_kb/db.py): DATABASE_URL,
# else these Cloud SQL settings. Nothing else reads them; Supabase stays the
# store for accounts and pipeline state either way.
CLOUD_SQL_CONNECTION_NAME = os.environ.get("CLOUD_SQL_CONNECTION_NAME", "")
DB_USER = os.environ.get("DB_USER", "")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "")
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

# The production's poster (agent_visual key art). Unlike the text models above,
# these ids come from Google's image-generation docs (September 2026) rather
# than a live key, so both stay env-overridable. Any model in the chain must
# accept a portrait 2:3 aspect ratio.
GEMINI_IMAGE_MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image")
GEMINI_IMAGE_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get("GEMINI_IMAGE_FALLBACK_MODELS", "gemini-2.5-flash-image").split(",")
    if m.strip()
]

# Guardrails
MAX_NEGOTIATION_ITERATIONS = 2  # never unbounded (AGENT.md Section 1)
MAX_ASSET_REGENERATIONS = 2     # agent_visual retry cap

# Budget-driven scale: the total budget entered at intake sets every cap below.
DEFAULT_BUDGET_USD = 250_000
CASTING_CAP_SHARE = 0.10    # max quote for a single role, as a share of the total budget
LOCATIONS_SHARE = 0.15      # share of the total budget available for venues
PERSONA_COUNT = 200         # synthetic viewers per screening (AGENT.md Phase V)

# Vertex AI through Google Cloud credentials (ADC), in place of a Gemini key.
# Opt-in only: the SDK's own GOOGLE_GENAI_USE_VERTEXAI switch plus a project.
# gcloud credentials on the machine are not enough on their own, so a
# "zero-key" run never spends anyone's Google Cloud credits by accident.
USE_VERTEX = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower() in ("1", "true", "yes", "on")
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
GOOGLE_CLOUD_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
VERTEX_FLASH_MODEL = os.environ.get("VERTEX_FLASH_MODEL", "gemini-2.5-flash")
VERTEX_PRO_MODEL = os.environ.get("VERTEX_PRO_MODEL", "gemini-2.5-flash")  # strictly use Flash to save credits
VERTEX_IMAGE_MODEL = os.environ.get("VERTEX_IMAGE_MODEL", "gemini-2.5-flash-image")
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get(
    "GOOGLE_APPLICATION_CREDENTIALS",
    str(Path.home() / ".config" / "gcloud" / "application_default_credentials.json"),
)


def has_adc() -> bool:
    """True if Google Cloud Application Default Credentials exist locally."""
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return Path(os.environ["GOOGLE_APPLICATION_CREDENTIALS"]).exists()
    default_adc = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if default_adc.exists():
        return True
    legacy = Path.home() / ".config" / "gcloud" / "legacy_credentials"
    return legacy.exists() and any(legacy.glob("*/adc.json"))


def has_vertex() -> bool:
    """True when the Vertex path is switched on, has a project, and has credentials."""
    return USE_VERTEX and bool(GOOGLE_CLOUD_PROJECT) and has_adc()


def has_gemini() -> bool:
    return bool(GEMINI_API_KEY) or has_vertex()


def has_tavily() -> bool:
    return bool(TAVILY_API_KEY)


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


def has_cloudsql() -> bool:
    return bool(CLOUD_SQL_CONNECTION_NAME and DB_USER and DB_PASS and DB_NAME)


def has_database() -> bool:
    """Return whether the actor KB can use a PostgreSQL connection."""
    return bool(DATABASE_URL) or has_cloudsql()
