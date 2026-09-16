"""The model tier picks the model: Pro for heavy reasoning, Flash otherwise,
each followed by the fallback chain so a retired model degrades the run. Image
calls walk their own chain and say why a model painted nothing."""
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


def test_the_vertex_path_respects_its_own_tier_settings(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "VERTEX_PRO_MODEL", "vertex-pro")
    monkeypatch.setattr(config, "VERTEX_FLASH_MODEL", "vertex-flash")
    assert gemini_client._candidates("pro") == ["vertex-pro", "vertex-flash"]
    assert gemini_client._candidates("flash") == ["vertex-flash"]


def _reply(parts=None, finish_reason="STOP"):
    content = SimpleNamespace(parts=parts) if parts is not None else None
    return SimpleNamespace(prompt_feedback=None, candidates=[SimpleNamespace(content=content, finish_reason=finish_reason)])


def test_the_first_inline_image_is_read_and_a_refusal_says_why():
    words = SimpleNamespace(inline_data=None, text="Here is your poster")
    picture = SimpleNamespace(inline_data=SimpleNamespace(data=b"\x89PNG", mime_type="image/png"))
    assert gemini_client._first_image(_reply([words, picture])) == (b"\x89PNG", "image/png", "")
    refused = _reply(finish_reason=SimpleNamespace(value="IMAGE_SAFETY"))
    assert gemini_client._first_image(refused) == (None, "", "finished with IMAGE_SAFETY")


def test_an_image_model_that_paints_nothing_hands_over_to_the_next(monkeypatch):
    monkeypatch.setattr(config, "has_gemini", lambda: True)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "key")
    monkeypatch.setattr(config, "GEMINI_IMAGE_MODEL", "painter")
    monkeypatch.setattr(config, "GEMINI_IMAGE_FALLBACK_MODELS", ["painter", "older-painter"])
    calls = []

    def generate_content(model, contents, config):
        calls.append(model)
        if model == "painter":
            return _reply(finish_reason=SimpleNamespace(value="IMAGE_SAFETY"))
        return _reply([SimpleNamespace(inline_data=SimpleNamespace(data=b"art", mime_type="image/png"))])

    client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    monkeypatch.setattr(gemini_client, "_get_client", lambda: client)
    image, mime, trace = gemini_client.generate_image_traced("a lone figure under a glowing sky")

    assert calls == ["painter", "older-painter"], "a refusal is not retried on the same model"
    assert (image, mime) == (b"art", "image/png")
    assert trace == {"source": "gemini", "model": "older-painter", "attempts": 2, "fell_back": True}

    monkeypatch.setattr(config, "GEMINI_IMAGE_FALLBACK_MODELS", [])
    image, _, trace = gemini_client.generate_image_traced("a lone figure under a glowing sky")
    assert image is None
    assert trace["reason"] == "all_models_failed" and "IMAGE_SAFETY" in trace["error"]
