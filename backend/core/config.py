"""Central configuration. Reads env vars (.env locally, the host's env settings when deployed).

Every external key is optional: with no keys set, the whole pipeline runs on
mock data so anyone can develop and demo without credentials.

What is read, and what for. Every service here has a free plan, and Lumen
uses nothing beyond it:
  - A model provider: all agent reasoning, as JSON. Any of Cerebras
    (CEREBRAS_API_KEY), Groq (GROQ_API_KEY), Gemini (GEMINI_API_KEY) or a local
    Ollama (OLLAMA_HOST) will serve it, tried in the order LUMEN_LLM_PROVIDERS
    gives. Gemini stays on its free tier: no Google Search grounding, image
    generation or Vertex AI.
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

# ------------------------------------------------------------ model access --
#
# Which providers may serve a call, most preferred first. A provider with no
# credentials is skipped, so this is a preference rather than a requirement: the
# same list works on a laptop with an Ollama running, on a free Cerebras key and
# on the deploy, which has only GEMINI_API_KEY set. Every one of them has a free
# plan and Lumen uses nothing beyond it.
#
# Cerebras leads because its free tier allows far more requests a day than
# Gemini's, which is what makes the audience evaluation in backend/eval
# runnable in one sitting rather than across a week of quota resets.
LLM_PROVIDERS = [
    name.strip().lower()
    for name in os.environ.get("LUMEN_LLM_PROVIDERS", "cerebras,groq,gemini,ollama").split(",")
    if name.strip()
]

# Model tiering (AGENT.md guardrails): the "flash" tier by default, "pro" only
# for heavy reasoning. Each provider names its own pair, and unset falls back to
# the flash model — a provider that offers nothing heavier is not a problem.
#
# Model ids move. Only the Gemini pair below is verified against a live key; the
# rest are the current free-tier ids for each provider and may be renamed or
# retired without notice. A 404 on one moves to the next candidate rather than
# failing the run, and every id is env-overridable.
GEMINI_FLASH_MODEL = os.environ.get("GEMINI_FLASH_MODEL", "gemini-3.6-flash")
GEMINI_PRO_MODEL = os.environ.get("GEMINI_PRO_MODEL", "gemini-3.6-flash")
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
CEREBRAS_FLASH_MODEL = os.environ.get("CEREBRAS_FLASH_MODEL", "qwen-3.8-27b")
CEREBRAS_PRO_MODEL = os.environ.get("CEREBRAS_PRO_MODEL", "gpt-oss-120b")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_FLASH_MODEL = os.environ.get("GROQ_FLASH_MODEL", "openai/gpt-oss-20b")
GROQ_PRO_MODEL = os.environ.get("GROQ_PRO_MODEL", "openai/gpt-oss-120b")
# Ollama needs no key: a host that answers is the credential. Blank disables it
# even when it is named in LLM_PROVIDERS, so the chain never waits on a port
# nothing is listening to.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "").rstrip("/")
OLLAMA_FLASH_MODEL = os.environ.get("OLLAMA_FLASH_MODEL", "llama3.1:8b")
OLLAMA_PRO_MODEL = os.environ.get("OLLAMA_PRO_MODEL", "")

# Tried in order when a provider's configured model is unavailable (404 retired
# / 429 quota / 503 overloaded), so a run degrades instead of dying. Gemini's
# only: the other providers fall through to the next provider instead, their
# free tiers being wide enough that a 429 means something is actually wrong.
GEMINI_FALLBACK_MODELS = [
    m.strip()
    for m in os.environ.get(
        "GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash,gemini-3-flash-preview"
    ).split(",")
    if m.strip()
]

# The longest a rate-limited call will wait before giving up on a model. Twenty
# seconds is right for a request someone is waiting on: past that, falling back
# to sample output beats holding the page. A batch job wants the opposite, and
# `eval.run predict` raises it, because on a free tier a 429 asking for 40
# seconds is the normal case and treating it as a failure turns a whole
# evaluation into a grading of its own fallbacks.
LLM_MAX_RETRY_WAIT_S = float(os.environ.get("LLM_MAX_RETRY_WAIT_S") or "20")

# Per-request timeout (ms) and bounded concurrency for batched agent work. Both
# read their old GEMINI_* names too, so an existing .env keeps working.
LLM_TIMEOUT_MS = int(os.environ.get("LLM_TIMEOUT_MS") or os.environ.get("GEMINI_TIMEOUT_MS") or "60000")
# How much of an uploaded screenplay a single model read gets (profiler, scene
# breakdown, audience analysis). 120k characters covers a full feature script.
SCRIPT_ANALYSIS_MAX_CHARS = int(os.environ.get("SCRIPT_ANALYSIS_MAX_CHARS", "120000"))
LLM_MAX_CONCURRENCY = int(os.environ.get("LLM_MAX_CONCURRENCY") or os.environ.get("GEMINI_MAX_CONCURRENCY") or "3")

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


def has_cerebras() -> bool:
    return bool(CEREBRAS_API_KEY)


def has_groq() -> bool:
    return bool(GROQ_API_KEY)


def has_ollama() -> bool:
    """A reachable host is Ollama's only credential, so a blank OLLAMA_HOST is
    what "not configured" means. Nothing here probes the port: an unreachable
    host fails its one attempt and the chain moves on."""
    return bool(OLLAMA_HOST)


def has_llm() -> bool:
    """Whether any provider can serve a call. False is the zero-key demo, where
    every agent returns its own sample output."""
    return bool(configured_llm_providers())


def configured_llm_providers() -> list[str]:
    """LLM_PROVIDERS, in order, less the ones with no credentials.

    The checks are looked up when this runs rather than captured once, so a test
    that disables a provider disables it here too — which is the whole of the
    offline guarantee in tests/conftest.py.
    """
    checks = {
        "gemini": has_gemini,
        "cerebras": has_cerebras,
        "groq": has_groq,
        "ollama": has_ollama,
    }
    return [name for name in LLM_PROVIDERS if checks.get(name, lambda: False)()]


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
