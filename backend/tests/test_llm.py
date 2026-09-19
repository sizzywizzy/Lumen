"""Model access: which provider serves a call, what the request looks like, and
whether the answer is allowed to be called live.

Three things are checked here, and the third is the one that matters most. The
tier picks the model — pro for heavy reasoning, flash otherwise, each followed by
its fallbacks, so a retired model degrades a run instead of ending it. Every
request is a plain JSON request, the only kind Lumen makes: nothing asks for
Gemini's paid-only features. And sample output is never reported as a model's
answer, whichever provider answered.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import config
from services import llm


def _providers(monkeypatch, *names):
    """Configure exactly these providers, in this order, with nothing else."""
    monkeypatch.setattr(config, "LLM_PROVIDERS", list(names))
    for provider, check in (
        ("gemini", "has_gemini"), ("cerebras", "has_cerebras"),
        ("groq", "has_groq"), ("ollama", "has_ollama"),
    ):
        monkeypatch.setattr(config, check, (lambda p: lambda: p in names)(provider))


# ------------------------------------------------------- which model, and whose --


def test_pro_tier_uses_the_pro_model_first(monkeypatch):
    _providers(monkeypatch, "gemini")
    monkeypatch.setattr(config, "GEMINI_PRO_MODEL", "pro-model")
    monkeypatch.setattr(config, "GEMINI_FLASH_MODEL", "flash-model")
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODELS", ["flash-model", "older-flash"])
    assert llm._candidates("pro") == [
        ("gemini", "pro-model"), ("gemini", "flash-model"), ("gemini", "older-flash")]
    assert llm._candidates("flash") == [("gemini", "flash-model"), ("gemini", "older-flash")]
    assert llm._candidates("anything else") == [("gemini", "flash-model"), ("gemini", "older-flash")]


def test_the_chain_is_the_configured_order_and_skips_what_has_no_key(monkeypatch):
    """LLM_PROVIDERS is a preference, not a requirement: the same setting has to
    work on a laptop running Ollama and on the deploy, which has one key."""
    monkeypatch.setattr(config, "CEREBRAS_FLASH_MODEL", "cb")
    monkeypatch.setattr(config, "GROQ_FLASH_MODEL", "gq")
    monkeypatch.setattr(config, "GEMINI_FLASH_MODEL", "gm")
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODELS", [])

    _providers(monkeypatch, "cerebras", "groq", "gemini")
    assert llm._candidates("flash") == [("cerebras", "cb"), ("groq", "gq"), ("gemini", "gm")]

    _providers(monkeypatch, "groq", "gemini")  # no Cerebras key on this machine
    assert llm._candidates("flash") == [("groq", "gq"), ("gemini", "gm")]

    _providers(monkeypatch)  # the zero-key demo
    assert llm._candidates("flash") == [] and config.has_llm() is False


def test_a_provider_with_no_heavier_model_serves_pro_from_its_flash_one(monkeypatch):
    """Answering a pro call with a smaller model beats not answering it, and the
    trace says which model it was."""
    _providers(monkeypatch, "ollama")
    monkeypatch.setattr(config, "OLLAMA_FLASH_MODEL", "llama3.1:8b")
    monkeypatch.setattr(config, "OLLAMA_PRO_MODEL", "")
    assert llm._candidates("pro") == [("ollama", "llama3.1:8b")]


# ------------------------------------------------------------- what is sent --


def test_a_gemini_request_is_plain_json_text(monkeypatch):
    """No tools (Google Search grounding) and no image output: both are paid-only."""
    _providers(monkeypatch, "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "key")
    sent = []

    def generate_content(model, contents, config):
        sent.append(config)
        return SimpleNamespace(text='{"ok": true}')

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(llm, "_get_gemini", lambda: client)
    assert llm.generate_json_traced("hi", system="Be brief.")[0] == {"ok": True}
    assert sent == [{"system_instruction": "Be brief.", "response_mime_type": "application/json"}]


@pytest.mark.parametrize(
    "provider, key_name, url",
    [
        ("cerebras", "CEREBRAS_API_KEY", "https://api.cerebras.ai/v1/chat/completions"),
        ("groq", "GROQ_API_KEY", "https://api.groq.com/openai/v1/chat/completions"),
    ],
)
def test_the_openai_compatible_providers_ask_for_a_json_object(monkeypatch, provider, key_name, url):
    """Both speak the OpenAI chat shape, so one implementation serves them, and
    `response_format` is what keeps the answer parseable."""
    _providers(monkeypatch, provider)
    monkeypatch.setattr(config, key_name, "sekret")
    monkeypatch.setattr(config, f"{provider.upper()}_FLASH_MODEL", "some-model")
    sent = []

    def post(url_, payload, headers):
        sent.append((url_, payload, headers))
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(llm, "_post_json", post)
    data, trace = llm.generate_json_traced("hi", system="Be brief.")

    assert data == {"ok": True}
    assert trace["provider"] == provider and trace["model"] == "some-model"
    assert llm.is_live(trace)
    (sent_url, payload, headers) = sent[0]
    assert sent_url == url
    assert headers["Authorization"] == "Bearer sekret"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["messages"][:2] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "hi"},
    ]


def test_ollama_is_asked_for_json_on_its_own_host(monkeypatch):
    _providers(monkeypatch, "ollama")
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://localhost:11434")
    monkeypatch.setattr(config, "OLLAMA_FLASH_MODEL", "llama3.1:8b")
    sent = []

    def post(url, payload, headers):
        sent.append((url, payload))
        return {"message": {"content": '{"ok": true}'}}

    monkeypatch.setattr(llm, "_post_json", post)
    data, trace = llm.generate_json_traced("hi")
    assert data == {"ok": True} and trace["provider"] == "ollama"
    assert sent[0][0] == "http://localhost:11434/api/chat"
    assert sent[0][1]["format"] == "json" and sent[0][1]["stream"] is False


def test_the_paid_only_features_are_not_in_the_code():
    source = Path(llm.__file__).read_text(encoding="utf-8")
    code = source.split('"""', 2)[2]  # past the module docstring, which names them
    for paid in ("google_search", "GoogleSearch", "response_modalities", "ImageConfig", "vertexai"):
        assert paid not in code, paid
    assert not hasattr(llm, "generate_json_with_search")
    assert not hasattr(llm, "generate_image_traced")


# --------------------------------------------------- live, or sample output --


def test_only_an_answered_call_counts_as_live():
    """`is_live` is the single definition, and the one place that decides whether
    a page may present a number as a model's work. A trace that does not say
    reads as sample output: the failure has to land on that side."""
    assert llm.is_live({"live": True, "source": "cerebras"}) is True
    assert llm.is_live({"live": False, "source": llm.MOCK}) is False
    assert llm.is_live({"source": "cerebras"}) is False  # said nothing: not live
    assert llm.is_live({}) is False and llm.is_live(None) is False


def test_sample_output_names_no_provider(monkeypatch):
    """With nothing configured, the caller gets its own mock back and the trace
    says so — no model, no provider, and a reason the dashboard can print."""
    _providers(monkeypatch)
    data, trace = llm.generate_json_traced("hi", mock={"stub": True})
    assert data == {"stub": True}
    assert trace["source"] == llm.MOCK and trace["provider"] is None
    assert trace["reason"] == "no_api_key" and not llm.is_live(trace)


def test_a_call_with_no_provider_and_no_sample_output_raises(monkeypatch):
    _providers(monkeypatch)
    with pytest.raises(llm.LLMUnavailable):
        llm.generate_json_traced("hi")


def test_a_recording_counts_answered_calls_and_fallbacks(monkeypatch):
    """What the pages read to say which parts of a plan are sample output."""
    _providers(monkeypatch)
    with llm.recording() as tally:
        llm.generate_json_traced("hi", mock={"stub": True})
        _providers(monkeypatch, "gemini")
        monkeypatch.setattr(config, "GEMINI_API_KEY", "key")
        client = SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda model, contents, config: SimpleNamespace(text='{"ok": true}')))
        monkeypatch.setattr(llm, "_get_gemini", lambda: client)
        llm.generate_json_traced("hi")
        # batched agent work runs in threads, which start with an empty context
        llm.map_concurrent([1, 2], lambda item: llm.generate_json_traced("hi"))

    assert tally == {"live": 3, "sample": 1, "reasons": ["no_api_key"]}
    llm.generate_json_traced("hi")  # outside the block: counted nowhere, and no error


# ----------------------------------------------------------- when it goes wrong --


class _RateLimited(Exception):
    def __init__(self, delay):
        super().__init__("429 RESOURCE_EXHAUSTED. You exceeded your current quota")
        self.details = {"error": {"code": 429, "details": [
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}}


def _flaky_client(error, calls):
    """A client whose first call fails with `error` and later calls answer."""
    def generate_content(model, contents, config):
        calls.append(model)
        if len(calls) == 1:
            raise error
        return SimpleNamespace(text='{"ok": true}')

    return SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))


def _one_chain(monkeypatch):
    _providers(monkeypatch, "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(config, "GEMINI_FLASH_MODEL", "first")
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODELS", ["second"])


def test_a_rate_limited_call_waits_as_long_as_google_asks(monkeypatch):
    _one_chain(monkeypatch)
    calls, slept = [], []
    monkeypatch.setattr(llm, "_get_gemini", lambda: _flaky_client(_RateLimited("7s"), calls))
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    data, trace = llm.generate_json_traced("hi")
    assert data == {"ok": True} and calls == ["first", "first"]
    assert 7 <= slept[0] < 7.5 and trace["model"] == "first"


def test_a_long_wait_is_spent_on_the_next_model_instead(monkeypatch):
    _one_chain(monkeypatch)
    calls, slept = [], []
    monkeypatch.setattr(llm, "_get_gemini", lambda: _flaky_client(_RateLimited("45s"), calls))
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    data, trace = llm.generate_json_traced("hi")
    assert data == {"ok": True} and calls == ["first", "second"] and slept == []
    assert trace["fell_back"] is True


def test_a_model_that_ran_out_of_time_is_not_retried(monkeypatch):
    """A 504 comes after the whole timeout; the next model is the faster bet."""
    _one_chain(monkeypatch)
    calls, slept = [], []
    timed_out = RuntimeError("504 DEADLINE_EXCEEDED. Deadline expired before operation could complete.")
    monkeypatch.setattr(llm, "_get_gemini", lambda: _flaky_client(timed_out, calls))
    monkeypatch.setattr(llm.time, "sleep", slept.append)
    data, trace = llm.generate_json_traced("hi")
    assert data == {"ok": True} and calls == ["first", "second"] and slept == []
    assert trace["fell_back"] is True


def test_an_exhausted_provider_hands_the_call_to_the_next_one(monkeypatch):
    """The point of the chain: Cerebras out of quota should cost the run nothing
    more than a provider, and the trace has to name the one that answered."""
    _providers(monkeypatch, "cerebras", "groq")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "a")
    monkeypatch.setattr(config, "GROQ_API_KEY", "b")
    monkeypatch.setattr(config, "CEREBRAS_FLASH_MODEL", "cb")
    monkeypatch.setattr(config, "GROQ_FLASH_MODEL", "gq")
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    tried = []

    def post(url, payload, headers):
        tried.append(payload["model"])
        if payload["model"] == "cb":
            raise llm._AttemptFailed("HTTP 429: out of tokens for today", status=429)
        return {"choices": [{"message": {"content": '{"ok": true}'}}]}

    monkeypatch.setattr(llm, "_post_json", post)
    data, trace = llm.generate_json_traced("hi")
    assert data == {"ok": True}
    assert tried == ["cb", "cb", "gq"]  # retried once, then handed on
    assert trace["provider"] == "groq" and trace["fell_back"] is True and llm.is_live(trace)


def test_every_provider_failing_falls_back_to_sample_output(monkeypatch):
    """A run must finish. The trace carries the reason and the last error so the
    report can say what went wrong instead of quietly grading the fallbacks."""
    _providers(monkeypatch, "cerebras")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "a")
    monkeypatch.setattr(config, "CEREBRAS_FLASH_MODEL", "cb")
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)
    monkeypatch.setattr(llm, "_post_json", lambda *a, **k: (_ for _ in ()).throw(
        llm._AttemptFailed("HTTP 500: upstream fell over", status=500)))

    data, trace = llm.generate_json_traced("hi", mock={"stub": True})
    assert data == {"stub": True} and not llm.is_live(trace)
    assert trace["reason"] == "all_models_failed" and "500" in trace["error"]


# ------------------------------------------------- the request, over a socket --


class _Canned(BaseHTTPRequestHandler):
    """Answers one POST: a fenced JSON body, or a 429 for the model "limited"."""

    seen: list = []

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's spelling
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).seen.append((self.path, body))
        if body.get("model") == "limited":
            payload, status, extra = b'{"error":"slow down"}', 429, {"Retry-After": "9"}
        else:
            # Fenced on purpose: the smaller open models do this despite being
            # asked for JSON, and `_extract_json` is what makes it survivable.
            payload = json.dumps({"message": {"content": '```json\n{"ok": true}\n```'}}).encode()
            status, extra = 200, {}
        self.send_response(status)
        for name, value in {"Content-Type": "application/json", **extra}.items():
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass  # keep the test output clean


@pytest.fixture
def canned_server():
    """A real HTTP server on a loopback port.

    Everything above patches `_post_json` away, which leaves the urllib call, the
    header parsing and the HTTPError handling untested — and a bug in any of them
    would turn every live call into a silent fallback. This exercises them for
    real without reaching the network.
    """
    _Canned.seen = []
    server = HTTPServer(("127.0.0.1", 0), _Canned)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", _Canned.seen
    finally:
        server.shutdown()


def test_a_real_post_is_sent_parsed_and_reported_live(monkeypatch, canned_server):
    host, seen = canned_server
    _providers(monkeypatch, "ollama")
    monkeypatch.setattr(config, "OLLAMA_HOST", host)
    monkeypatch.setattr(config, "OLLAMA_FLASH_MODEL", "llama3.1:8b")

    data, trace = llm.generate_json_traced("hello", system="Be brief.")
    assert data == {"ok": True} and llm.is_live(trace) and trace["provider"] == "ollama"
    assert seen[0][0] == "/api/chat" and seen[0][1]["model"] == "llama3.1:8b"


def test_a_rate_limit_over_http_is_read_from_the_retry_after_header(monkeypatch, canned_server):
    host, _seen = canned_server
    monkeypatch.setattr(config, "OLLAMA_HOST", host)
    with pytest.raises(llm._AttemptFailed) as raised:
        llm._call_ollama("limited", "hello", None, None)

    assert raised.value.status == 429 and raised.value.retry_after == 9.0
    assert llm._retryable(raised.value)
    assert 9 <= llm._backoff(raised.value, 0) < 9.5


def test_an_unreachable_host_costs_one_attempt_and_falls_back(monkeypatch):
    """A port nothing listens to is the normal state of a machine with no Ollama
    running, so it must not stall a run."""
    _providers(monkeypatch, "ollama")
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://127.0.0.1:1")
    monkeypatch.setattr(config, "OLLAMA_FLASH_MODEL", "llama3.1:8b")
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)

    data, trace = llm.generate_json_traced("hello", mock={"stub": True})
    assert data == {"stub": True} and not llm.is_live(trace)
    assert trace["reason"] == "all_models_failed"


# ------------------------------------------------------ asking for a shape --


def test_a_schema_is_derived_from_the_sample_output_an_agent_already_has():
    """One source of truth: the `mock` an agent falls back to is by construction
    the shape it expects, so nothing has to be written twice."""
    schema = llm.schema_from_example(
        {"score": 7, "lift": 1.5, "flag": False, "note": "x", "tags": ["a"], "nested": {"k": 1}}
    )
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False  # strict: nothing unnamed
    assert schema["required"] == ["flag", "lift", "nested", "note", "score", "tags"]
    kinds = {key: value.get("type") for key, value in schema["properties"].items()}
    # A bool is an int in Python; read in that order it would be an integer here.
    assert kinds == {
        "score": "integer", "lift": "number", "flag": "boolean",
        "note": "string", "tags": "array", "nested": "object",
    }
    assert schema["properties"]["tags"]["items"] == {"type": "string"}


def test_what_an_example_cannot_show_is_left_open():
    """An empty list says nothing about its items, and a provider wants an object
    at the root, so a bare list or scalar cannot be a schema at all."""
    assert llm.schema_from_example({"rows": []})["properties"]["rows"] == {"type": "array"}
    assert llm.schema_from_example({"maybe": None})["properties"]["maybe"] == {}
    assert llm.schema_from_example([1, 2]) is None
    assert llm.schema_from_example("text") is None
    assert llm.schema_from_example(None) is None


def test_violations_name_the_field_and_the_reason():
    schema = llm.schema_from_example({"score": 7, "note": "x", "tags": ["a"], "nested": {"k": 1}})
    good = {"score": 7, "note": "x", "tags": ["a"], "nested": {"k": 1}}
    assert llm.violations(good, schema) == []
    assert llm.violations({k: v for k, v in good.items() if k != "note"}, schema) == ["note: missing"]
    assert llm.violations({**good, "score": "high"}, schema) == [
        "score: expected an integer, got a string"]
    assert llm.violations({**good, "extra": 1}, schema) == ["extra: not in the shape"]
    assert llm.violations({**good, "tags": ["a", 7]}, schema) == [
        "tags[1]: expected a string, got an integer"]
    assert llm.violations({**good, "nested": {"k": "no"}}, schema) == [
        "nested.k: expected an integer, got a string"]
    assert llm.violations({**good, "nested": []}, schema) == [
        "nested: expected an object, got an array"]
    assert llm.violations(good, None) == []  # no schema, nothing to violate


def test_an_integer_where_a_number_is_asked_for_is_not_a_violation():
    """JSON has one number type, and a model answering 7 for 7.0 is right."""
    schema = llm.schema_from_example({"lift": 1.5})
    assert llm.violations({"lift": 2}, schema) == []
    assert llm.violations({"lift": True}, schema) == ["lift: expected a number, got a boolean"]


def test_gemini_gets_a_schema_without_the_keyword_it_refuses(monkeypatch):
    """Found by a live call: Gemini's `response_schema` is an OpenAPI subset and
    answers 400 INVALID_ARGUMENT on `additionalProperties`, which OpenAI-style
    strict mode requires. So the dialects differ, and only Gemini's is stripped."""
    schema = llm.schema_from_example({"a": 1, "nested": {"b": "x"}, "rows": [{"c": True}]})
    gemini = json.dumps(llm._schema_for("gemini", schema))
    assert "additionalProperties" not in gemini  # at every depth, not just the root
    assert all(word in gemini for word in ("required", "properties", "items"))
    for provider in ("cerebras", "groq", "ollama"):
        assert llm._schema_for(provider, schema) == schema
    assert llm._schema_for("gemini", None) is None


def test_each_provider_is_asked_to_enforce_the_schema_its_own_way(monkeypatch):
    schema = llm.schema_from_example({"ok": True})

    _providers(monkeypatch, "cerebras")
    monkeypatch.setattr(config, "CEREBRAS_API_KEY", "k")
    monkeypatch.setattr(config, "CEREBRAS_FLASH_MODEL", "m")
    sent = []
    monkeypatch.setattr(llm, "_post_json", lambda url, payload, headers: (
        sent.append(payload), {"choices": [{"message": {"content": '{"ok": true}'}}]})[1])
    _data, trace = llm.generate_json_traced("hi", schema=schema)
    assert sent[0]["response_format"]["type"] == "json_schema"
    assert sent[0]["response_format"]["json_schema"]["strict"] is True
    assert trace["schema"] is True

    _providers(monkeypatch, "ollama")
    monkeypatch.setattr(config, "OLLAMA_HOST", "http://h")
    monkeypatch.setattr(config, "OLLAMA_FLASH_MODEL", "m")
    sent.clear()
    monkeypatch.setattr(llm, "_post_json", lambda url, payload, headers: (
        sent.append(payload), {"message": {"content": '{"ok": true}'}})[1])
    llm.generate_json_traced("hi", schema=schema)
    assert sent[0]["format"] == schema  # Ollama takes the schema outright

    _providers(monkeypatch, "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    settings = []
    client = SimpleNamespace(models=SimpleNamespace(
        generate_content=lambda model, contents, config: (
            settings.append(config), SimpleNamespace(text='{"ok": true}'))[1]))
    monkeypatch.setattr(llm, "_get_gemini", lambda: client)
    llm.generate_json_traced("hi", schema=schema)
    assert settings[0]["response_schema"]["type"] == "object"
    assert "additionalProperties" not in settings[0]["response_schema"]


def test_a_call_without_a_schema_still_only_asks_for_json(monkeypatch):
    """No agent passes a schema yet, so the unenforced request is what ships and
    must not change shape."""
    _providers(monkeypatch, "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(config, "GROQ_FLASH_MODEL", "m")
    sent = []
    monkeypatch.setattr(llm, "_post_json", lambda url, payload, headers: (
        sent.append(payload), {"choices": [{"message": {"content": '{"ok": true}'}}]})[1])
    _data, trace = llm.generate_json_traced("hi")
    assert sent[0]["response_format"] == {"type": "json_object"}
    assert trace["schema"] is False


def test_every_request_names_itself(monkeypatch, canned_server):
    """Cloudflare fronts at least one provider and answers urllib's default
    `Python-urllib/3.12` with 403 "error code: 1010". Every call came back that
    way until an agent was set, and the body is the only thing that says so —
    a 403 otherwise reads as an outage or a bad key."""
    host, seen = canned_server
    _providers(monkeypatch, "ollama")
    monkeypatch.setattr(config, "OLLAMA_HOST", host)
    monkeypatch.setattr(config, "OLLAMA_FLASH_MODEL", "m")

    sent_headers = {}
    original = llm._post_json
    monkeypatch.setattr(llm, "_post_json", lambda url, payload, headers: (
        sent_headers.update(headers), original(url, payload, headers))[1])
    llm.generate_json_traced("hi")

    assert "urllib" not in llm.USER_AGENT.lower()
    assert llm.USER_AGENT.startswith("Lumen/")
    assert seen  # it really went over the socket


def test_json_object_mode_says_the_word_json(monkeypatch):
    """Groq answers 400 "'messages' must contain the word 'json' in some form"
    when `response_format` asks for `json_object` and nothing in the messages
    says so. Almost none of Lumen's prompts use the word, so without this every
    agent call fails on Groq — found by making one."""
    _providers(monkeypatch, "groq")
    monkeypatch.setattr(config, "GROQ_API_KEY", "k")
    monkeypatch.setattr(config, "GROQ_FLASH_MODEL", "m")
    sent = []
    monkeypatch.setattr(llm, "_post_json", lambda url, payload, headers: (
        sent.append(payload), {"choices": [{"message": {"content": '{"ok": true}'}}]})[1])

    llm.generate_json_traced("Name a genre.", system="Be brief.")
    said = " ".join(m["content"] for m in sent[0]["messages"]).lower()
    assert "json" in said

    # A prompt that already says it is left alone: nothing is added twice.
    sent.clear()
    llm.generate_json_traced("Reply as JSON with a genre.")
    assert len(sent[0]["messages"]) == 1

    # And an enforced schema needs none of this — the schema is the instruction.
    sent.clear()
    llm.generate_json_traced("Name a genre.", schema=llm.schema_from_example({"g": "x"}))
    assert len(sent[0]["messages"]) == 1
