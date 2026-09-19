"""The evaluation harness, checked offline.

The metrics decide whether a claim about Lumen's accuracy is true, so they are
tested against hand-computed answers rather than against themselves. The rest
of the file guards the two ways an evaluation quietly lies: grading offline
fallbacks as though a model produced them, and printing a headline number from
a run that never finished.
"""
import json

import pytest

from eval import metrics, predictors, run


# ------------------------------------------------------------------ level --


def test_mae_rmse_bias_against_hand_computed_values():
    # errors: +2, -4, +6 -> |e| mean 4, signed mean 4/3, rms sqrt(56/3)
    pairs = [(72.0, 70.0), (66.0, 70.0), (86.0, 80.0)]
    assert metrics.mae(pairs) == pytest.approx(4.0)
    assert metrics.bias(pairs) == pytest.approx(4 / 3)
    assert metrics.rmse(pairs) == pytest.approx((56 / 3) ** 0.5)


def test_a_perfect_predictor_scores_zero_error():
    pairs = [(70.0, 70.0), (55.0, 55.0), (91.0, 91.0)]
    assert metrics.mae(pairs) == 0.0
    assert metrics.rmse(pairs) == 0.0
    assert metrics.spearman(pairs) == pytest.approx(1.0)


# ------------------------------------------------------------------ order --


def test_spearman_is_one_for_order_preserved_and_minus_one_for_reversed():
    rising = [(1.0, 10.0), (2.0, 20.0), (3.0, 30.0), (4.0, 40.0)]
    assert metrics.spearman(rising) == pytest.approx(1.0)
    falling = [(1.0, 40.0), (2.0, 30.0), (3.0, 20.0), (4.0, 10.0)]
    assert metrics.spearman(falling) == pytest.approx(-1.0)


def test_a_constant_predictor_has_no_ranking_ability():
    """The trap the report exists to expose: respectable MAE, zero ordering."""
    pairs = [(70.0, 68.0), (70.0, 72.0), (70.0, 66.0), (70.0, 74.0)]
    assert metrics.mae(pairs) == pytest.approx(3.0)
    assert metrics.spearman(pairs) == 0.0
    assert metrics.pearson(pairs) == 0.0


def test_tied_predictions_share_a_rank():
    # Without tie-averaging the correlation would depend on input order.
    assert metrics._ranks([5.0, 5.0, 9.0]) == [1.5, 1.5, 3.0]
    assert metrics._ranks([3.0, 1.0, 2.0]) == [3.0, 1.0, 2.0]


def test_permutation_p_is_small_for_a_real_pattern_and_large_for_noise():
    perfect = [(float(i), float(i)) for i in range(12)]
    assert metrics.permutation_p(perfect, rounds=500) < 0.05
    flat = [(1.0, 5.0), (1.0, 9.0), (1.0, 2.0), (1.0, 7.0)]
    assert metrics.permutation_p(flat, rounds=500) == pytest.approx(1.0)


def test_permutation_p_is_reproducible():
    pairs = [(float(i), float((i * 7) % 11)) for i in range(11)]
    assert metrics.permutation_p(pairs, rounds=400) == metrics.permutation_p(pairs, rounds=400)


# --------------------------------------------------------------- contrast --


def test_paired_bootstrap_detects_a_clear_win():
    close = [(70.0, 70.0)] * 20
    far = [(90.0, 70.0)] * 20
    result = metrics.paired_bootstrap_mae(close, far, rounds=500)
    assert result["mae_gap"] == pytest.approx(-20.0)
    assert result["verdict"] == "lower error than the baseline"


def test_paired_bootstrap_admits_when_it_cannot_tell():
    same = [(70.0, 68.0), (66.0, 70.0), (80.0, 77.0), (59.0, 62.0)]
    result = metrics.paired_bootstrap_mae(same, list(same), rounds=500)
    assert result["mae_gap"] == pytest.approx(0.0)
    assert result["verdict"] == "no measurable difference on this sample"
    assert result["ci95_low"] <= 0 <= result["ci95_high"]


def test_paired_bootstrap_refuses_mismatched_samples():
    with pytest.raises(AssertionError):
        metrics.paired_bootstrap_mae([(1.0, 2.0)], [(1.0, 2.0), (3.0, 4.0)])


# ------------------------------------------------ fallbacks are not scores --


def _film(tmdb_id: int, actual: float) -> dict:
    return {"tmdb_id": tmdb_id, "title": f"Film {tmdb_id}", "actual_audience_score": actual,
            "genres": ["Drama"], "runtime_min": 100, "overview": "x" * 200,
            "release_date": "2026-07-01"}


def test_a_film_whose_prediction_fell_back_is_not_graded():
    """The whole point of `live`: a mock's number must never enter the metrics."""
    films = [_film(1, 70.0), _film(2, 80.0), _film(3, 60.0)]
    store = {"lumen": {
        "1": {"audience_score": 72.0, "live": True},
        "2": {"audience_score": 68.0, "live": False},   # fell back
        "3": {"audience_score": None, "live": False},   # failed outright
    }}
    usable = run._usable(films, store, ["lumen"])
    assert [f["tmdb_id"] for f in usable] == [1]


def test_paired_grading_drops_a_film_either_predictor_missed():
    films = [_film(1, 70.0), _film(2, 80.0)]
    store = {
        "lumen": {"1": {"audience_score": 72.0, "live": True},
                  "2": {"audience_score": 75.0, "live": True}},
        "single_call": {"1": {"audience_score": 69.0, "live": True},
                        "2": {"audience_score": 70.0, "live": False}},
    }
    assert [f["tmdb_id"] for f in run._usable(films, store, ["lumen", "single_call"])] == [1]


def test_brief_analysis_invents_nothing():
    """A synopsis has no themes, characters or content flags in it, so the
    offline analysis must not supply any."""
    analysis = predictors.analysis_from_brief(_film(1, 70.0))
    assert analysis["themes"] == []
    assert analysis["main_characters"] == []
    assert analysis["content_flags"] == []
    assert analysis["material_quality"]["completeness"] == "synopsis"
    # Only dimensions a plot summary can honestly speak to.
    assert "dialogue" not in analysis["evaluable_dimensions"]
    assert "story" in analysis["evaluable_dimensions"]


def test_the_brief_never_names_the_film():
    film = _film(1, 70.0)
    film["title"] = "Some Very Distinctive Title"
    from eval import dataset
    assert "Some Very Distinctive Title" not in dataset.brief(film)


# ------------------------------------------------------------- the report --


def _payload(**overrides) -> dict:
    base = {
        "generated_at": "2026-09-19T00:00:00Z",
        "snapshot": {"fetched_at": "2026-09-19T00:00:00Z",
                     "ground_truth": "TMDb vote_average x 10",
                     "query": {"primary_release_date.gte": "2026-06-01",
                               "primary_release_date.lte": "2026-09-19",
                               "vote_count.gte": 100},
                     "eligibility": {}},
        "films_in_snapshot": 31, "films_graded": 31, "films_attempted": {"lumen": 31},
        "live_share": 1.0, "withheld": False, "dropped_for_leakage": [],
        "models_used": {"lumen": ["gemini-3.6-flash"]},
        "constant_baseline_value": 71.7,
        "results": {"lumen": metrics.score([(72.0, 70.0), (66.0, 70.0), (86.0, 80.0)]),
                    "constant": metrics.score([(71.7, 70.0), (71.7, 70.0), (71.7, 80.0)])},
        "contrasts": {}, "tomatometer_ordering": None,
    }
    base.update(overrides)
    return base


def test_report_warns_loudly_when_the_run_did_not_finish():
    text = run.render_markdown(_payload(live_share=0.45, withheld=True, films_graded=14))
    assert "Incomplete run" in text
    assert "45%" in text


def test_a_finished_report_carries_no_warning_and_states_its_limits():
    text = run.render_markdown(_payload())
    assert "Incomplete run" not in text
    assert "MAE" in text
    assert "gemini-3.6-flash" in text
    # The caveats are part of the report, not optional decoration.
    assert "not Rotten Tomatoes" in text
    assert "Titles are withheld" in text


def test_report_names_films_dropped_for_leakage():
    text = run.render_markdown(_payload(dropped_for_leakage=["Some Recalled Film"]))
    assert "Some Recalled Film" in text


def test_report_is_valid_json_round_trip():
    assert json.loads(json.dumps(_payload()))["films_graded"] == 31


# ------------------------------------------------- drift between eval and prod --
# The evaluation is only evidence about the shipped system while it keeps
# grading the shipped system. Each test below pins a constant or a mapping that
# the eval borrows from production, so a later change to one side fails here
# instead of quietly making the report describe something else.


def test_the_liked_threshold_is_the_products_own_object():
    """`tomatometer` means "share of viewers at or above LIKED_SCORE". If the eval
    kept its own copy, changing the product's threshold would leave the report
    grading the old definition."""
    from domains.launch.agents import phase5_audience
    assert predictors.LIKED_SCORE is phase5_audience.LIKED_SCORE


def test_the_eval_panel_is_the_products_panel():
    from core import config
    assert predictors.EVAL_PANEL_SIZE == config.PERSONA_COUNT


def test_the_derived_analysis_names_only_dimensions_the_simulator_weights():
    """A dimension with no weight is dropped silently, and the weighted overall
    would then be computed over fewer dimensions than the prompt asked for."""
    from domains.launch.agents import audience_sim
    analysis = predictors.analysis_from_brief(
        {"runtime_min": 100, "genres": ["Drama"], "overview": "x" * 200})
    assert audience_sim.evaluable_dimensions(analysis) == analysis["evaluable_dimensions"]


def test_tmdb_genre_names_reach_the_persona_vocabulary():
    """TMDb writes "Science Fiction"; personas speak "sci-fi". When the mapping
    misses, every viewer is flagged as outside the genre and the genre-affinity
    split silently flattens across the whole sample."""
    from core.audience import personas as panel_lib
    assert panel_lib.normalise_genres(["Science Fiction"]) == ["sci-fi"]
    assert panel_lib.normalise_genres(["Thriller", "Drama"]) == ["thriller", "drama"]
    assert panel_lib.normalise_genres(["Animation", "Family"]) == ["animation"]


# ------------------------------------------------------ the committed sample --


def test_the_committed_snapshot_still_satisfies_its_own_query():
    """Guards the sample against a later edit that breaks the premise: a film
    from before the cutoff, or one with too few ratings to have a stable actual."""
    from eval import dataset
    if not dataset.SNAPSHOT.exists():
        pytest.skip("no film snapshot committed yet")
    snapshot = dataset.load()
    query = snapshot["query"]
    assert snapshot["films"], "a snapshot with no films is a broken evaluation"
    assert len(snapshot["films"]) >= 30, "the evaluation claims 30+ films"
    for film in snapshot["films"]:
        assert film["release_date"] >= query["primary_release_date.gte"], film["title"]
        assert film["release_date"] <= query["primary_release_date.lte"], film["title"]
        assert film["vote_count"] >= query["vote_count.gte"], film["title"]
        assert 0 <= film["actual_audience_score"] <= 100, film["title"]
        assert len(film["overview"]) >= dataset.MIN_OVERVIEW_CHARS, film["title"]
        assert film["runtime_min"] >= dataset.MIN_RUNTIME_MIN, film["title"]
        assert not set(film["genres"]) & dataset.EXCLUDED_GENRES, film["title"]


def test_the_sample_has_enough_spread_to_rank():
    """A sample where every film scored the same cannot show ranking ability, so
    a rho computed over it would be meaningless whatever it came out as."""
    import statistics

    from eval import dataset
    if not dataset.SNAPSHOT.exists():
        pytest.skip("no film snapshot committed yet")
    actuals = [f["actual_audience_score"] for f in dataset.load()["films"]]
    assert statistics.pstdev(actuals) >= 5.0, f"spread {statistics.pstdev(actuals):.1f} is too flat"


# ----------------------------------------------------------- resumability --


def test_a_resumed_run_keeps_live_rows_and_retries_the_rest(tmp_path, monkeypatch):
    """The quota case, which is the normal case on a free tier: a second run must
    not re-spend calls on films already scored live, and must retry the ones that
    fell back."""
    from eval import dataset
    snapshot = {"fetched_at": "x", "ground_truth": "x", "eligibility": {},
                "query": {"primary_release_date.gte": "2026-06-01",
                          "primary_release_date.lte": "2026-09-19", "vote_count.gte": 100},
                "candidates_seen": 2, "skipped_ineligible": 0,
                "films": [_film(1, 70.0), _film(2, 80.0)]}
    monkeypatch.setattr(dataset, "SNAPSHOT", dataset.save(snapshot, tmp_path / "films.json"))
    monkeypatch.setattr(run, "PREDICTIONS", tmp_path / "predictions.json")
    run._save(tmp_path / "predictions.json", {"lumen": {
        "1": {"audience_score": 77.7, "live": True},          # keep
        "2": {"audience_score": 65.0, "live": False},         # retry
    }})

    assert run.main(["predict", "--predictor", "lumen", "--delay", "0",
                     "--panel-size", "40"]) == 0
    rows = json.loads((tmp_path / "predictions.json").read_text(encoding="utf-8"))["lumen"]
    assert rows["1"]["audience_score"] == 77.7, "a live row is kept, not re-spent"
    assert rows["2"]["live"] is False, "the fallen-back film was retried (and fell back again)"
    assert rows["2"].get("panel_size") == 40, "the retry actually ran the simulator"
