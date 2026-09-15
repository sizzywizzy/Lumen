"""The model tier picks the model: Pro for heavy reasoning, Flash otherwise,
each followed by the fallback chain so a retired model degrades the run."""
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
