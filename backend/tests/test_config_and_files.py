"""Configuration and the local JSON files: quoted .env values, Gemini only
through an API key, and writes that never leave half a file behind."""
import json
import os

import pytest

from core import config
from services import json_files


@pytest.mark.parametrize("raw, value", [
    ("abc", "abc"), (' "abc" ', "abc"), ("'abc'", "abc"), ('"a=b"', "a=b"),
    ('"abc', '"abc'), ("", ""), ('""', ""), ("it's", "it's"),
])
def test_env_values_lose_only_matching_quotes(raw, value):
    assert config._env_value(raw) == value


def test_gemini_needs_an_api_key(monkeypatch):
    """Only a key reaches Gemini; Google Cloud credentials on the machine never do."""
    from services import gemini_client

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(gemini_client, "_client", None)
    with pytest.raises(gemini_client.GeminiUnavailable):
        gemini_client._get_client()


def test_a_write_replaces_the_file_whole_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "rows.json"
    json_files.write_json(target, [{"n": 1}])
    json_files.write_json(target, [{"n": 2}], indent=2)
    assert json_files.read_json(target) == [{"n": 2}]
    assert [p.name for p in tmp_path.iterdir()] == ["rows.json"]
    assert json_files.read_json(tmp_path / "missing.json", default=[]) == []


def test_a_failed_write_keeps_the_previous_file(tmp_path):
    target = tmp_path / "rows.json"
    json_files.write_json(target, {"ok": True})
    with pytest.raises(TypeError):
        json_files.write_json(target, {"bad": object()})
    assert json.loads(target.read_text(encoding="utf-8")) == {"ok": True}
    assert [p.name for p in tmp_path.iterdir()] == ["rows.json"]


def test_a_busy_target_is_retried(tmp_path, monkeypatch):
    """Windows refuses to replace a file another handle has open."""
    real = os.replace
    failures = iter([PermissionError("in use"), PermissionError("in use")])

    def flaky(src, dst):
        error = next(failures, None)
        if error:
            raise error
        real(src, dst)

    monkeypatch.setattr(json_files.os, "replace", flaky)
    monkeypatch.setattr(json_files.time, "sleep", lambda seconds: None)
    json_files.write_json(tmp_path / "rows.json", [1])
    assert json_files.read_json(tmp_path / "rows.json") == [1]


def test_the_stores_write_through_the_atomic_helper(state_dir):
    from services import auth_store, simulation_store, skill_store

    simulation_store.save({"project_id": "PROJ_T", "simulation_id": "SIM_1", "created_at": "x"})
    simulation_store.save_panel("PROJ_T", "SIM_1", {"personas": []})
    skill_store.save({"project_id": "PROJ_T", "run_id": "RUN_1", "created_at": "x"})
    auth_store._write("cn_users", [])
    leftovers = [p for p in state_dir.rglob("*") if p.name.endswith(".tmp")]
    assert leftovers == []
    assert simulation_store.list_for_project("PROJ_T")[0]["simulation_id"] == "SIM_1"
    assert simulation_store.get_panel("PROJ_T", "SIM_1") == {"personas": []}
