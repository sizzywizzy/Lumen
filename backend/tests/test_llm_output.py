"""Coercion of model output: a wrong type falls back to the mock's value."""
import pytest

from core import llm_output as L


@pytest.mark.parametrize("value, expected", [
    (7, 7.0), ("7.5", 7.5), (250, 100.0), (-3, 0.0),
    ("high", 50.0), (None, 50.0), (True, 50.0), (float("nan"), 50.0), ([7], 50.0),
])
def test_number_clamps_and_falls_back(value, expected):
    assert L.number(value, 50, 0, 100) == expected


@pytest.mark.parametrize("value, default, expected", [
    (True, False, True), ("false", True, False), ("Yes", False, True), (0, True, False),
    (1, False, True), ("maybe", True, True), (None, False, False), ([], True, True),
])
def test_boolean_reads_the_usual_spellings(value, default, expected):
    assert L.boolean(value, default) is expected


@pytest.mark.parametrize("value, expected", [
    ("  hi ", "hi"), ("", "d"), (None, "d"), ({"a": 1}, "d"), (7, "7"), (True, "d"), ("x" * 10, "xxx"),
])
def test_text_strips_falls_back_and_clips(value, expected):
    assert L.text(value, "d", 3) == expected


def test_mapping_and_listing_copy_their_defaults():
    default = {"a": 1}
    out = L.mapping(["not a dict"], default)
    assert out == default and out is not default
    assert L.mapping({"b": 2}) == {"b": 2}
    assert L.listing("nope", [1]) == [1]
    assert L.listing([2]) == [2]
    assert L.listing(None) == []


def test_codes_read_as_words_and_prose_is_left_alone():
    assert L.words("EXPOSITION_OVERLOAD") == "exposition overload"
    assert L.words("Too much exposition in act two") == "Too much exposition in act two"
    assert L.words("UAE") == "UAE"
    assert L.words(None) == ""
