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

# Model tiering (AGENT.md guardrails): Flash by default, Pro only for heavy reasoning.
GEMINI_FLASH_MODEL = os.environ.get("GEMINI_FLASH_MODEL", "gemini-2.0-flash")
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-2.0-pro")

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


def has_supabase() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)
