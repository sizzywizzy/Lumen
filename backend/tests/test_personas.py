"""Seeded persona generation.

The promise this module makes is reproducibility: the same (seed, size,
distribution) must yield byte-identical personas, or a stored simulation can
never be audited or re-run.
"""
from core.audience import personas as P


def test_same_seed_is_byte_identical():
    assert P.build_panel(size=40, seed=1234)[0] == P.build_panel(size=40, seed=1234)[0]


def test_different_seed_produces_a_different_panel():
    assert P.build_panel(size=40, seed=1234)[0] != P.build_panel(size=40, seed=5678)[0]


def test_panel_size_and_ids_are_exact():
    people, _ = P.build_panel(size=17, seed=1)
    assert [p["persona_id"] for p in people] == [f"AUD_{i:04d}" for i in range(17)]


def test_no_sensitive_attributes_are_modelled():
    """Deliberate design rule: taste and viewing behaviour only."""
    people, _ = P.build_panel(size=25, seed=7)
    forbidden = {"gender", "ethnicity", "religion", "income", "race", "sexuality"}
    assert forbidden.isdisjoint(people[0])


def test_language_is_plausible_for_the_market():
    people, _ = P.build_panel(size=120, seed=99)
    for person in people:
        assert person["language_preference"] in P.MARKETS[person["market"]]["languages"]


def test_distribution_override_restricts_the_panel_and_leaves_others_default():
    people, resolved = P.build_panel(
        size=60, seed=3, distribution={"market": {"IN": 0.7, "AE": 0.3}}
    )
    assert {p["market"] for p in people} <= {"IN", "AE"}
    assert resolved["age_group"] == P.DEFAULT_DISTRIBUTION["age_group"]


def test_genre_fans_are_present_but_never_the_whole_panel():
    """A panel with no sceptics would be useless, so the boost is capped."""
    people, _ = P.build_panel(size=200, seed=11, film_genres=["thriller"])
    assert 0 < sum(p["matches_film_genre"] for p in people) < len(people)


def test_normalise_genres_tokenises_compound_labels():
    assert P.normalise_genres(["neo-noir thriller"]) == ["thriller", "crime"]
    assert P.normalise_genres(None) == []


def test_cohorts_stay_within_the_llm_fan_out_ceiling():
    people, _ = P.build_panel(size=500, seed=20260902, film_genres=["thriller"])
    assert len(P.build_cohorts(people)) <= P.MAX_COHORTS
