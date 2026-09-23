"""Model access — the ONLY place LLM calls happen.

Guardrails (AGENT.md): the `flash` tier by default, `pro` only for heavy
reasoning, and structured JSON output always (never parse prose). With no
provider configured the caller gets its `mock` value back, so the whole pipeline
demos offline.

**Four providers, one chain.** `config.LLM_PROVIDERS` lists which may serve a
call and in what order; a provider with no credentials is skipped, so the same
setting works on a laptop, on a free key and on the deploy. Each has a free plan
and Lumen uses nothing beyond it:

  - **Cerebras** and **Groq** — OpenAI-compatible JSON endpoints, and the reason
    this module exists in this shape. Their free tiers allow far more requests a
    day than Gemini's, which is what makes the evaluation in `backend/eval`
    finishable in one sitting instead of across a week of quota resets.
  - **Gemini** — free tier, API key, JSON text requests. No paid-only features
    (Google Search grounding, image generation) and no Vertex AI. Install
    `google-genai` before setting a real key.
  - **Ollama** — a local model, no key and no quota. For debugging a prompt
    without spending anyone's allowance.

**Saying which.** `generate_json_traced` returns what actually happened: the
provider, the model, whether it fell back, and `live` — whether a real model
answered at all. Ask that question with `is_live()` and never by comparing
`source` to a provider name: the string used to be `"gemini"` in eight places,
and every one of them would have called a Cerebras answer a mock on the day a
second provider arrived. A trace with no `live` key reads as not-live, so the
failure lands on the side of under-claiming.

`recording()` counts live and sample calls for a block of work, which is how a
plan can say which of its parts came from Lumen's sample output.

`generate_json` keeps its original signature, so agents are unchanged.
"""
import contextvars
import json
import random
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Callable, Iterable, Iterator, Optional

from core import config, llm_output

# The `source` of a trace that carries sample output rather than a model answer.
MOCK = "mock"

_gemini = None
_gemini_lock = threading.Lock()

# The count kept for the block of work running now, or None when nobody asked.
_tally: contextvars.ContextVar[Optional[dict[str, Any]]] = contextvars.ContextVar("llm_tally", default=None)
_tally_lock = threading.Lock()

# Statuses worth another attempt on the same model. 504 is deliberately absent:
# the model already took the whole timeout, so a retry would likely wait that
# long again. Anything else moves straight on to the next candidate.
_RETRYABLE_STATUS = {429, 500, 502, 503}
_RETRYABLE_TEXT = ("RESOURCE_EXHAUSTED", "UNAVAILABLE", "INTERNAL")
_GONE_STATUS = {404}
_GONE_TEXT = ("NOT_FOUND",)
# A rate-limited reply can say how long to wait. Longer waits than this are
# better spent on the next candidate, whose quota is its own — read from config
# at call time so a batch job can raise it without the product inheriting it.

# Sent on every provider request; see `_post_json`.
USER_AGENT = "Lumen/1.0 (+https://github.com/swatikumari/Lumen)"

# The OpenAI-compatible providers, and where their JSON endpoint lives.
_OPENAI_COMPATIBLE = {
    "cerebras": "https://api.cerebras.ai/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
}


class LLMUnavailable(RuntimeError):
    """Every candidate failed. Carries the last error for reporting."""


class _AttemptFailed(RuntimeError):
    """One (provider, model) attempt that returned no usable JSON.

    Carries the provider's own `status` and `retry_after` where it gave them, so
    the retry policy reads fields instead of guessing from a message.
    """

    def __init__(self, message: str, *, status: Optional[int] = None, retry_after: Optional[float] = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


# ------------------------------------------------------------- what happened --


def is_live(trace: Optional[dict[str, Any]]) -> bool:
    """Whether this trace records a real model answer rather than sample output.

    The one definition. A trace that does not say reads as not live, so a caller
    that forgets to set it under-reports liveness rather than presenting sample
    output as a model's work.
    """
    return bool((trace or {}).get("live"))


# --------------------------------------------------------- describing a shape --


def schema_from_example(example: Any) -> Optional[dict[str, Any]]:
    """A JSON Schema for the shape of `example`, or None if it cannot be one.

    Every agent already supplies a `mock`: the value it falls back to, which is
    by construction the shape it expects back. Deriving the schema from that
    keeps one source of truth — a hand-written schema beside each prompt would be
    a second one, and the two would drift.

    Strict enough for the providers that want strictness: every key present is
    required and nothing else is allowed, which is what OpenAI-style
    `json_schema` with `strict` demands.

    It cannot describe what an example does not show, and there are three such
    gaps. An empty list says nothing about its items, so the array is left
    unconstrained. A mock's free-form map (a `metadata` bag, say) is read as a
    fixed set of keys, which is tighter than the agent really wants. And a list's
    later items are assumed to match the first. `eval/structured` reports how
    many prompts got a usable schema for exactly this reason.
    """
    shape = _shape(example)
    # Providers want an object at the root; a bare list or scalar cannot be one.
    return shape if shape.get("type") == "object" else None


def _shape(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        properties = {str(key): _shape(item) for key, item in value.items()}
        return {
            "type": "object",
            "properties": properties,
            "required": sorted(properties),
            "additionalProperties": False,
        }
    if isinstance(value, list):
        return {"type": "array", "items": _shape(value[0])} if value else {"type": "array"}
    if isinstance(value, bool):  # before int: a bool is an int in Python
        return {"type": "boolean"}
    if isinstance(value, int):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    return {}  # None, or anything else: say nothing rather than guess


def violations(value: Any, schema: Optional[dict[str, Any]], path: str = "") -> list[str]:
    """Where `value` departs from `schema`, as dotted paths with the reason.

    The measurement half of `schema_from_example`: valid JSON in the wrong shape
    is the failure that a schema is supposed to prevent, and this is what counts
    it. Deliberately small — enough for the shapes the derivation above produces,
    not a general JSON Schema validator, and no dependency.
    """
    if not schema:
        return []
    here = path or "(root)"
    expected = schema.get("type")

    if expected == "object":
        if not isinstance(value, dict):
            return [f"{here}: expected an object, got {_name(value)}"]
        found = []
        for key in schema.get("required", []):
            if key not in value:
                found.append(f"{path}.{key}".lstrip(".") + ": missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in schema.get("properties", {}):
                    found.append(f"{path}.{key}".lstrip(".") + ": not in the shape")
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                found += violations(value[key], sub, f"{path}.{key}".lstrip("."))
        return found

    if expected == "array":
        if not isinstance(value, list):
            return [f"{here}: expected an array, got {_name(value)}"]
        items = schema.get("items")
        return [v for index, item in enumerate(value) for v in violations(item, items, f"{path}[{index}]")]

    if expected == "boolean" and not isinstance(value, bool):
        return [f"{here}: expected a boolean, got {_name(value)}"]
    if expected == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        return [f"{here}: expected an integer, got {_name(value)}"]
    # An integer where a number is asked for is not a violation; JSON has one
    # number type and a model answering 7 for 7.0 is right.
    if expected == "number" and (isinstance(value, bool) or not isinstance(value, (int, float))):
        return [f"{here}: expected a number, got {_name(value)}"]
    if expected == "string" and not isinstance(value, str):
        return [f"{here}: expected a string, got {_name(value)}"]
    return []


def _schema_for(provider: str, schema: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The same shape written in the dialect a provider will accept.

    There is no one dialect. An OpenAI-style `json_schema` with `strict` requires
    `additionalProperties: false` on every object; Gemini's `response_schema` is
    an OpenAPI subset that has no such keyword and answers 400 INVALID_ARGUMENT
    when it sees one. So the strict form is the one `schema_from_example` builds,
    and Gemini's copy has that keyword taken out.

    The consequence is worth knowing when reading results: on Gemini a schema
    cannot forbid extra fields, only require the ones named. Violation rates are
    therefore comparable between arms on one provider, and not between providers.
    """
    if not schema:
        return None
    return _without(schema, "additionalProperties") if provider == "gemini" else schema


def _without(schema: Any, keyword: str) -> Any:
    if isinstance(schema, dict):
        return {key: _without(value, keyword) for key, value in schema.items() if key != keyword}
    if isinstance(schema, list):
        return [_without(item, keyword) for item in schema]
    return schema


def _name(value: Any) -> str:
    return {
        type(None): "null", bool: "a boolean", int: "an integer",
        float: "a number", str: "a string", list: "an array", dict: "an object",
    }.get(type(value), type(value).__name__)


@contextmanager
def recording() -> Iterator[dict[str, Any]]:
    """Count the calls made inside the block: {live, sample, reasons}.

    The orchestrator opens one per phase, so a plan can say which of its parts
    the model wrote and which fell back to an agent's sample output.
    """
    tally: dict[str, Any] = {"live": 0, "sample": 0, "reasons": []}
    token = _tally.set(tally)
    try:
        yield tally
    finally:
        _tally.reset(token)


def _record(live: bool, reason: str = "") -> None:
    tally = _tally.get()
    if tally is None:
        return
    with _tally_lock:  # batched agent work counts from several threads
        tally["live" if live else "sample"] += 1
        if reason and reason not in tally["reasons"]:
            tally["reasons"].append(reason)


# ----------------------------------------------------------- which model next --


def _tier_models(provider: str, tier: str) -> list[str]:
    """The models to try for one provider at one tier, most preferred first.

    A provider that names nothing heavier for `pro` serves it from the flash
    model: a smaller model answering is better than no answer, and the trace
    records which one it was.
    """
    if provider == "gemini":
        preferred = config.GEMINI_PRO_MODEL if tier == "pro" else config.GEMINI_FLASH_MODEL
        # Gemini's chain is its own: its free tier is narrow enough that a 429
        # on one model often clears on another.
        return [preferred, config.GEMINI_FLASH_MODEL, *config.GEMINI_FALLBACK_MODELS]
    pairs = {
        "cerebras": (config.CEREBRAS_FLASH_MODEL, config.CEREBRAS_PRO_MODEL),
        "groq": (config.GROQ_FLASH_MODEL, config.GROQ_PRO_MODEL),
        "ollama": (config.OLLAMA_FLASH_MODEL, config.OLLAMA_PRO_MODEL),
    }
    flash, pro = pairs.get(provider, ("", ""))
    return [pro or flash] if tier == "pro" else [flash]


def _candidates(tier: str) -> list[tuple[str, str]]:
    """Every (provider, model) to try, in order, for a tier.

    Providers in the configured order, each contributing its own models, so a
    retired model, an exhausted quota or an unreachable host degrades the run
    instead of ending it.
    """
    ordered: list[tuple[str, str]] = []
    for provider in config.configured_llm_providers():
        for model in _tier_models(provider, tier):
            if model and (provider, model) not in ordered:
                ordered.append((provider, model))
    return ordered


# ----------------------------------------------------------------- the calls --


def _extract_json(text: str) -> Any:
    """Models occasionally wrap JSON in a fence or preamble despite being asked
    for JSON, and the smaller open models do it more often than Gemini."""
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    try:
        return json.loads(cleaned)
    except Exception:
        # If response has reasoning prose or markdown, isolate the first JSON structure
        first_brace = cleaned.find("{")
        first_bracket = cleaned.find("[")
        if first_brace != -1 and (first_bracket == -1 or first_brace < first_bracket):
            last_brace = cleaned.rfind("}")
            if last_brace > first_brace:
                return json.loads(cleaned[first_brace : last_brace + 1])
        elif first_bracket != -1:
            last_bracket = cleaned.rfind("]")
            if last_bracket > first_bracket:
                return json.loads(cleaned[first_bracket : last_bracket + 1])
        raise


def _get_gemini():
    global _gemini
    with _gemini_lock:
        if _gemini is None:
            if not config.GEMINI_API_KEY:
                # Explicit, because `genai.Client()` without one would fall back
                # to whatever Google credentials the machine happens to have.
                raise LLMUnavailable("No Gemini access: set GEMINI_API_KEY.")
            from google import genai  # imported lazily so mock mode needs no install
            from google.genai import types

            _gemini = genai.Client(
                api_key=config.GEMINI_API_KEY,
                http_options=types.HttpOptions(timeout=config.LLM_TIMEOUT_MS),
            )
    return _gemini


def _gemini_retry_after(exc: Exception) -> Optional[float]:
    """The wait a Gemini 429 asks for, in seconds, when the reply carries one."""
    details = getattr(exc, "details", None)
    error = details.get("error", details) if isinstance(details, dict) else {}
    for item in (error.get("details") or []) if isinstance(error, dict) else []:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("RetryInfo"):
            try:
                return float(str(item.get("retryDelay", "")).rstrip("s"))
            except ValueError:
                return None
    return None


def _call_gemini(model: str, prompt: str, system: Optional[str], schema: Optional[dict]) -> Any:
    settings: dict[str, Any] = {
        "system_instruction": system,
        "response_mime_type": "application/json",
    }
    if schema:
        settings["response_schema"] = schema
    try:
        response = _get_gemini().models.generate_content(
            model=model,
            contents=prompt,
            config=settings,
        )
    except Exception as exc:  # noqa: BLE001 — the SDK raises many types; classify by message
        raise _AttemptFailed(
            f"{type(exc).__name__}: {exc}", retry_after=_gemini_retry_after(exc)
        ) from exc
    return _extract_json(response.text)


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    """One JSON POST, with the provider's status carried into the failure."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        # The agent is not decoration. Cloudflare fronts at least one of these
        # providers and answers urllib's default `Python-urllib/3.12` with
        # 403 "error code: 1010" — a blocked client signature, which looks
        # exactly like an outage until you read the body.
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.LLM_TIMEOUT_MS / 1000) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001 — a body we cannot read is not the error
            pass
        retry_after = None
        try:
            header = exc.headers.get("Retry-After") if exc.headers else None
            retry_after = float(header) if header else None
        except (TypeError, ValueError):
            retry_after = None
        raise _AttemptFailed(
            f"HTTP {exc.code}: {body}", status=exc.code, retry_after=retry_after
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise _AttemptFailed(f"{type(exc).__name__}: {exc}"[:300]) from exc


def _messages(prompt: str, system: Optional[str]) -> list[dict[str, str]]:
    system_part = [{"role": "system", "content": system}] if system else []
    return [*system_part, {"role": "user", "content": prompt}]


def _call_openai_compatible(
    provider: str, model: str, prompt: str, system: Optional[str], schema: Optional[dict]
) -> Any:
    """Cerebras and Groq both speak the OpenAI chat shape, including
    `response_format`, so one implementation serves both.

    Without a schema this asks for `json_object`: valid JSON, any shape. With one
    it asks for `json_schema` with `strict`, which is the difference the
    experiment in eval/structured measures. Not every model on either provider
    enforces `json_schema` — one that does not answers 400, and the chain moves
    to the next candidate rather than quietly returning an unenforced answer.
    """
    key = config.CEREBRAS_API_KEY if provider == "cerebras" else config.GROQ_API_KEY
    response_format: dict[str, Any] = (
        {"type": "json_schema", "json_schema": {"name": "reply", "strict": True, "schema": schema}}
        if schema else {"type": "json_object"}
    )
    messages = _messages(prompt, system)
    if not schema and not any("json" in m["content"].lower() for m in messages):
        # Groq refuses `json_object` outright unless the word appears in the
        # messages: 400 "'messages' must contain the word 'json' in some form".
        # Most of Lumen's prompts say "return"/"reply with" and never the word,
        # so without this every agent call fails on Groq. It asks for nothing new
        # — `response_format` already demands JSON — it just says so aloud.
        messages = [*messages, {"role": "system", "content": "Respond with JSON."}]
    body = _post_json(
        _OPENAI_COMPATIBLE[provider],
        {
            "model": model,
            "messages": messages,
            "response_format": response_format,
        },
        {"Authorization": f"Bearer {key}"},
    )
    choices = body.get("choices") or []
    if not choices:
        raise _AttemptFailed(f"{provider} returned no choices: {str(body)[:200]}")
    return _extract_json((choices[0].get("message") or {}).get("content") or "")


def _call_ollama(model: str, prompt: str, system: Optional[str], schema: Optional[dict]) -> Any:
    # Ollama's `format` takes either the word "json" or a JSON schema outright.
    body = _post_json(
        f"{config.OLLAMA_HOST}/api/chat",
        {
            "model": model,
            "messages": _messages(prompt, system),
            "format": schema or "json",
            "stream": False,
        },
        {},
    )
    return _extract_json((body.get("message") or {}).get("content") or "")


def _call(provider: str, model: str, prompt: str, system: Optional[str], schema: Optional[dict]) -> Any:
    dialect = _schema_for(provider, schema)
    if provider == "gemini":
        return _call_gemini(model, prompt, system, dialect)
    if provider in _OPENAI_COMPATIBLE:
        return _call_openai_compatible(provider, model, prompt, system, dialect)
    if provider == "ollama":
        return _call_ollama(model, prompt, system, dialect)
    raise _AttemptFailed(f"no caller for provider '{provider}'")


# --------------------------------------------------------- the retry policy --


def _status(exc: Exception) -> Optional[int]:
    """The HTTP status behind a failure: the one the provider reported, or the
    first three-digit code in a message (Gemini's SDK writes it there)."""
    status = getattr(exc, "status", None)
    if isinstance(status, int):
        return status
    for code in (*_RETRYABLE_STATUS, *_GONE_STATUS, 504):
        if str(code) in str(exc):
            return code
    return None


def _model_gone(exc: Exception) -> bool:
    return _status(exc) in _GONE_STATUS or any(text in str(exc) for text in _GONE_TEXT)


def _retryable(exc: Exception) -> bool:
    return _status(exc) in _RETRYABLE_STATUS or any(text in str(exc) for text in _RETRYABLE_TEXT)


def is_daily_limit(error: str) -> bool:
    """Whether a 429 is a day's budget rather than a minute's.

    The two look identical and are not. A per-minute limit clears while you
    wait, so waiting is right. A daily one refills at a trickle — Groq offered
    eleven minutes for the next 1,840 tokens — so a run that waits it out spends
    hours sleeping and still ends up grading its own fallbacks. Worth stopping
    for instead, and saying so.
    """
    text = (error or "").lower()
    return any(mark in text for mark in ("per day", "(tpd)", "(rpd)", "tpd:", "rpd:"))


def _backoff(exc: Exception, attempt: int) -> Optional[float]:
    """Seconds to wait before trying the same model again, or None to move on to
    the next candidate. Free tiers are rate-limited per minute and usually say
    how long to wait; waiting that long beats burning the retry at once."""
    if is_daily_limit(str(exc)):
        return None  # tomorrow's problem; do not sleep through it
    asked = getattr(exc, "retry_after", None)
    if asked is None:
        return 1.5 * (attempt + 1) + random.random()
    return asked + random.random() / 2 if asked <= config.LLM_MAX_RETRY_WAIT_S else None


# --------------------------------------------------------------- the surface --


def generate_json_traced(
    prompt: str,
    *,
    tier: str = "flash",
    system: Optional[str] = None,
    mock: Optional[dict[str, Any]] = None,
    schema: Optional[dict[str, Any]] = None,
    attempts_per_model: int = 2,
) -> tuple[Any, dict[str, Any]]:
    """Run a prompt and return (parsed_json, trace).

    trace = {live, source, provider, model, attempts, fell_back, schema, reason,
    error}, where `source` is the provider that answered or "mock". Ask whether a
    model answered with `is_live(trace)`.

    `schema` asks the provider to enforce a JSON Schema on the reply rather than
    merely to return JSON. No agent passes one yet: whether that is worth the
    coupling is what `eval/structured` measures, and `schema_from_example` builds
    one from the `mock` an agent already supplies.
    """
    if not config.has_llm():
        if mock is not None:
            _record(False, "no_api_key")
            return mock, {"live": False, "source": MOCK, "provider": None, "model": None,
                          "reason": "no_api_key"}
        raise LLMUnavailable(
            "No model provider is configured and this call has no sample output. "
            "Set one of CEREBRAS_API_KEY, GROQ_API_KEY, GEMINI_API_KEY or OLLAMA_HOST."
        )

    candidates = _candidates(tier)
    last_error = "" if candidates else (
        f"no model is named for tier '{tier}' by any of "
        f"{config.configured_llm_providers()} — check the *_FLASH_MODEL settings"
    )
    total_attempts = 0

    for index, (provider, model) in enumerate(candidates):
        for attempt in range(attempts_per_model):
            total_attempts += 1
            try:
                data = _call(provider, model, prompt, system, schema)
                _record(True)
                return data, {
                    "live": True,
                    "source": provider,
                    "provider": provider,
                    "model": model,
                    "attempts": total_attempts,
                    "fell_back": index > 0,
                    "schema": bool(schema),
                }
            except Exception as exc:  # noqa: BLE001 — classified below, never raised from here
                last_error = f"{type(exc).__name__}: {exc}"
                if _model_gone(exc):
                    break  # this model is gone; try the next candidate immediately
                wait = _backoff(exc, attempt) if _retryable(exc) else None
                if wait is not None and attempt + 1 < attempts_per_model:
                    time.sleep(wait)
                    continue
                break  # non-retryable (bad request, auth) — move to the next candidate

    if mock is not None:
        _record(False, "all_models_failed")
        return mock, {
            "live": False,
            "source": MOCK,
            "provider": None,
            "model": None,
            "reason": "all_models_failed",
            "error": last_error[:300],
        }
    raise LLMUnavailable(last_error or "Every configured provider failed.")


def generate_json(
    prompt: str,
    *,
    tier: str = "flash",
    system: Optional[str] = None,
    mock: Optional[dict[str, Any]] = None,
    schema: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Original contract, unchanged for existing agents."""
    data, _trace = generate_json_traced(
        prompt, tier=tier, system=system, mock=mock, schema=schema
    )
    return data


def map_concurrent(items: Iterable, worker: Callable, max_workers: Optional[int] = None) -> list:
    """Run `worker` over `items` with bounded concurrency, preserving order.

    Used by the audience simulator to fan cohort batches out without tripping a
    free tier's rate limit. Exceptions are returned in place, so one bad batch
    cannot abort the whole simulation.
    """
    items = list(items)
    if not items:
        return []
    workers = max(1, min(max_workers or config.LLM_MAX_CONCURRENCY, len(items)))
    # A worker thread starts with an empty context, so both counts are carried
    # in by hand: the calls made, and the repairs those answers needed.
    tally = _tally.get()
    repairs = llm_output.tally()

    def guarded(item):
        token = _tally.set(tally) if tally is not None else None
        try:
            with llm_output.adopt(repairs):
                return worker(item)
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller as a value
            return exc
        finally:
            if token is not None:
                _tally.reset(token)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(guarded, items))
