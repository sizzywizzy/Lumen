"""Central configuration. Reads env vars (Replit Secrets / .env / GCP Secret Manager).

Every external key is optional: with no keys set, the whole pipeline runs on
mock data so anyone can develop and demo without credentials.
"""
import os
from pathlib import Path

# Load a local .env if present (no python-dotenv dependency needed).
_env_file = Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

BACKEND_DIR = Path(__file__).resolve().parents[1]
MOCK_DATA_DIR = BACKEND_DIR / "mock_data"
LOCAL_STATE_DIR = BACKEND_DIR / ".state"  # fallback persistence when Supabase is not configured

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
WHISPER_API_KEY = os.environ.get("WHISPER_API_KEY", "")
IMAGEN_API_KEY = os.environ.get("IMAGEN_API_KEY", "")

# Google Cloud SQL configuration (takes precedence over Supabase when configured)
CLOUD_SQL_CONNECTION_NAME = os.environ.get("CLOUD_SQL_CONNECTION_NAME", "")
DB_USER = os.environ.get("DB_USER", "")
DB_PASS = os.environ.get("DB_PASS", "")
DB_NAME = os.environ.get("DB_NAME", "")

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


_supabase_warned = False


def has_supabase() -> bool:
    """True only when Supabase is configured AND the client library is present.

    Credentials in .env without `pip install supabase` used to take every store
    down the Supabase branch and raise ModuleNotFoundError on the first read.
    Falling back to the local JSON store keeps the app running and says so once.
    """
    global _supabase_warned
    if not (SUPABASE_URL and SUPABASE_KEY):
        return False
    try:
        import supabase  # noqa: F401
    except ImportError:
        if not _supabase_warned:
            _supabase_warned = True
            print(
                "[cinenode] SUPABASE_URL/KEY are set but the 'supabase' package is not "
                "installed - falling back to local JSON state under backend/.state/. "
                "Run: pip install supabase",
                flush=True,
            )
        return False
    return True


def has_cloudsql() -> bool:
    return bool(CLOUD_SQL_CONNECTION_NAME and DB_USER and DB_PASS and DB_NAME)
