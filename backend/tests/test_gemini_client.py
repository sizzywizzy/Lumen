"""The model tier picks the model: Pro for heavy reasoning, Flash otherwise,
each followed by the fallback chain so a retired model degrades the run. Every
request is a plain JSON text request, the only kind Lumen makes: nothing asks
for Gemini's paid-only features."""
from pathlib import Path
from types import SimpleNamespace

from core import config
from services import gemini_client


def test_pro_tier_uses_the_pro_model_first(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(config, "GEMINI_PRO_MODEL", "pro-model")
    monkeypatch.setattr(config, "GEMINI_FLASH_MODEL", "flash-model")
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODELS", ["flash-model", "older-flash"])
    assert gemini_client._candidates("pro") == ["pro-model", "flash-model", "older-flash"]
    assert gemini_client._candidates("flash") == ["flash-model", "older-flash"]
    assert gemini_client._candidates("anything else") == ["flash-model", "older-flash"]


def test_every_request_is_plain_json_text(monkeypatch):
    """No tools (Google Search grounding) and no image output: both are paid-only."""
    monkeypatch.setattr(config, "has_gemini", lambda: True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "key")
    sent = []

    def generate_content(model, contents, config):
        sent.append(config)
        return SimpleNamespace(text='{"ok": true}')

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(gemini_client, "_get_client", lambda: client)
    assert gemini_client.generate_json_traced("hi", system="Be brief.")[0] == {"ok": True}
    assert sent == [{"system_instruction": "Be brief.", "response_mime_type": "application/json"}]


def test_a_recording_counts_answered_calls_and_fallbacks(monkeypatch):
    """What the pages read to say which parts of a plan are sample output."""
    monkeypatch.setattr(config, "has_gemini", lambda: False)
    with gemini_client.recording() as tally:
        gemini_client.generate_json_traced("hi", mock={"stub": True})
        monkeypatch.setattr(config, "has_gemini", lambda: True)
        monkeypatch.setattr(config, "GEMINI_API_KEY", "key")
        client = SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda model, contents, config: SimpleNamespace(text='{"ok": true}')))
        monkeypatch.setattr(gemini_client, "_get_client", lambda: client)
        gemini_client.generate_json_traced("hi")
        # batched agent work runs in threads, which start with an empty context
        gemini_client.map_concurrent([1, 2], lambda item: gemini_client.generate_json_traced("hi"))

    assert tally == {"live": 3, "sample": 1, "reasons": ["no_api_key"]}
    gemini_client.generate_json_traced("hi")  # outside the block: counted nowhere, and no error


def test_the_paid_only_features_are_not_in_the_code():
    source = Path(gemini_client.__file__).read_text(encoding="utf-8")
    code = source.split('"""', 2)[2]  # past the module docstring, which names them
    for paid in ("google_search", "GoogleSearch", "response_modalities", "ImageConfig", "vertexai"):
        assert paid not in code, paid
    assert not hasattr(gemini_client, "generate_json_with_search")
    assert not hasattr(gemini_client, "generate_image_traced")


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
    monkeypatch.setattr(config, "has_gemini", lambda: True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(config, "GEMINI_FLASH_MODEL", "first")
    monkeypatch.setattr(config, "GEMINI_FALLBACK_MODELS", ["second"])


def test_a_rate_limited_call_waits_as_long_as_google_asks(monkeypatch):
    _one_chain(monkeypatch)
    calls, slept = [], []
    monkeypatch.setattr(gemini_client, "_get_client", lambda: _flaky_client(_RateLimited("7s"), calls))
    monkeypatch.setattr(gemini_client.time, "sleep", slept.append)
    data, trace = gemini_client.generate_json_traced("hi")
    assert data == {"ok": True} and calls == ["first", "first"]
    assert 7 <= slept[0] < 7.5 and trace["model"] == "first"


def test_a_long_wait_is_spent_on_the_next_model_instead(monkeypatch):
    _one_chain(monkeypatch)
    calls, slept = [], []
    monkeypatch.setattr(gemini_client, "_get_client", lambda: _flaky_client(_RateLimited("45s"), calls))
    monkeypatch.setattr(gemini_client.time, "sleep", slept.append)
    data, trace = gemini_client.generate_json_traced("hi")
    assert data == {"ok": True} and calls == ["first", "second"] and slept == []
    assert trace["fell_back"] is True


def test_a_model_that_ran_out_of_time_is_not_retried(monkeypatch):
    """A 504 comes after the whole timeout; the next model is the faster bet."""
    _one_chain(monkeypatch)
    calls, slept = [], []
    timed_out = RuntimeError("504 DEADLINE_EXCEEDED. Deadline expired before operation could complete.")
    monkeypatch.setattr(gemini_client, "_get_client", lambda: _flaky_client(timed_out, calls))
    monkeypatch.setattr(gemini_client.time, "sleep", slept.append)
    data, trace = gemini_client.generate_json_traced("hi")
    assert data == {"ok": True} and calls == ["first", "second"] and slept == []
    assert trace["fell_back"] is True
