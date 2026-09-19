"""Actor search recall, and the leak that would make the number meaningless.

An actor's stored record is `Actor: {name}. Biography: {bio}. Past roles:
{character} in {title}; ...` — so a brief that mentions the actor, the film or
the character is not testing a search, it is testing string matching, and would
report a high number for a system that does nothing. The first test here is the
one that matters; the rest check that the metrics say what they claim and that
the shipped ranking is what gets measured.
"""
import json

import pytest

from eval.casting import corpus, metrics, search
from eval.casting.labels import LABELS
from eval.casting.run import ACTORS, QUERIES
from services.casting_kb.tmdb import _norm

# Ordinary nouns that happen to sit inside a title or an honorific. The rule
# bars *names* — a word that identifies a person or a work. "Detective" in
# "Detective Loki" and "wedding" in "Monsoon Wedding" are what the part is, and
# a casting brief that could not say them would not be a casting brief. Each is
# listed rather than waved through by a loosened rule, so the judgement is
# visible to whoever reads this next.
ORDINARY = {"detective", "wrestler", "train", "queen", "portrait", "handmaiden", "wedding"}


def _queries():
    if not QUERIES.exists():
        pytest.skip("no queries.json; run `python -m eval.casting.run resolve`")
    return json.loads(QUERIES.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the leak --


def test_no_brief_names_the_actor_the_film_or_the_character():
    """The evaluation's one load-bearing rule, checked rather than remembered."""
    leaks = []
    for query in _queries()["queries"]:
        brief = _norm(query["brief"])
        words = set(brief.split())
        for label, phrase in (
            ("actor", query["answer"]["name"]),
            ("film", query["film"]["title"]),
            ("character", query["character"]),
        ):
            spelled = _norm(phrase)
            if spelled and spelled in brief:
                leaks.append(f"{query['film']['title']}: names the {label} ({phrase!r})")
            for token in spelled.split():
                if len(token) >= 5 and token in words and token not in ORDINARY:
                    leaks.append(f"{query['film']['title']}: brief uses {token!r} from the {label}")

    assert not leaks, (
        "these briefs would let the search match on a name instead of the part:\n  "
        + "\n  ".join(leaks)
    )


def test_every_allowed_ordinary_word_is_actually_used():
    """A permission nobody uses is a permission nobody reviewed. If a brief is
    rewritten, its exemption should go with it."""
    briefs = " ".join(_norm(q["brief"]) for q in _queries()["queries"]).split()
    unused = sorted(word for word in ORDINARY if word not in briefs)
    assert not unused, f"{unused} are allowed through the leak check but no brief uses them"


def test_every_brief_resolved_to_exactly_one_actor():
    resolved = _queries()
    assert resolved["resolved"] == len(LABELS), (
        f"{len(LABELS) - resolved['resolved']} briefs did not resolve: {resolved['unresolved']}"
    )
    ids = [q["id"] for q in resolved["queries"]]
    assert len(set(ids)) == len(ids), "two briefs resolved to the same film and actor"
    for query in resolved["queries"]:
        assert query["answer"]["tmdb_id"] and query["answer"]["name"]
        assert len(query["brief"]) > 80, f"{query['film']['title']}: the brief is too thin to rank on"


def test_the_part_a_brief_came_from_is_held_out(monkeypatch):
    """The answer's own credit for that film is removed before embedding. Left
    in, the record would contain the part being described and recall would be a
    measure of string matching."""
    person = {
        "id": 7,
        "name": "Someone",
        "biography": "A performer.",
        "known_for_department": "Acting",
        "birthday": "1970-01-01",
        "gender": 2,
        "combined_credits": {"cast": [
            {"id": 111, "character": "The Part In Question", "title": "Held Out", "popularity": 90},
            {"id": 222, "character": "Another Part", "title": "Kept", "popularity": 80},
        ]},
    }
    monkeypatch.setattr(corpus.tmdb, "fetch_person", lambda _id: person)

    kept = corpus._record(7, set())
    assert "The Part In Question" in kept["description"] and "Another Part" in kept["description"]

    held = corpus._record(7, {111})
    assert "The Part In Question" not in held["description"]
    assert "Held Out" not in held["description"]
    assert "Another Part" in held["description"], "holding one part out removed the rest too"


# ----------------------------------------------------------------- metrics --


def test_recall_and_mrr_against_hand_computed_answers():
    ranks = [1, 3, 11, None, 5]  # found first, third, eleventh, never, fifth
    assert metrics.recall_at(ranks, 5) == pytest.approx(3 / 5)
    assert metrics.recall_at(ranks, 10) == pytest.approx(3 / 5)
    assert metrics.recall_at(ranks, 11) == pytest.approx(4 / 5)
    assert metrics.mrr(ranks) == pytest.approx((1 + 1 / 3 + 1 / 11 + 0 + 1 / 5) / 5)
    assert metrics.recall_at([], 5) == 0.0 and metrics.mrr([]) == 0.0


def test_rank_of_is_one_based_and_says_when_it_missed():
    assert metrics.rank_of(42, [7, 42, 9]) == 2
    assert metrics.rank_of(42, [7, 9]) is None


def test_chance_is_k_over_the_corpus():
    """The line every other number has to clear."""
    assert metrics.chance_recall_at(10, 1000) == pytest.approx(0.01)
    assert metrics.chance_recall_at(10, 5) == 1.0  # ten of five is everyone
    assert metrics.chance_recall_at(10, 0) == 0.0


def test_the_interval_never_runs_off_the_scale():
    """Recall here sits near 0 or 1 often enough that a textbook normal interval
    would report a negative bound, which is not a share of anything."""
    low, high = metrics.wilson_interval(0, 50)
    assert low == 0.0 and 0 < high < 0.1
    low, high = metrics.wilson_interval(50, 50)
    assert high == 1.0 and 0.9 < low < 1.0
    assert metrics.wilson_interval(0, 0) == (0.0, 0.0)


def test_a_gap_that_is_only_this_sample_is_not_reported_as_real():
    """Two indexes that trade wins brief for brief have an interval crossing
    zero; one that wins everywhere does not."""
    alternating = metrics.paired_bootstrap([1, None] * 15, [None, 1] * 15, 10, rounds=500)
    assert alternating["low"] < 0 < alternating["high"]

    dominant = metrics.paired_bootstrap([1] * 30, [None] * 30, 10, rounds=500)
    assert dominant["gap"] == 1.0 and dominant["low"] > 0 and dominant["p"] == 0.0


# ------------------------------------------------------------------ ranking --


CORPUS = [
    {"actor_id": 1, "description": "Actor: A. Biography: a weathered rodeo rider and horse trainer."},
    {"actor_id": 2, "description": "Actor: B. Biography: a concert pianist and conservatory teacher."},
    {"actor_id": 3, "description": "Actor: C. Biography: a deep sea diver and marine salvage expert."},
]


def test_the_lexical_baseline_ranks_by_shared_words():
    ranked = search.build("lexical", CORPUS).rank("a pianist who teaches at a conservatory", 3)
    assert ranked[0] == 2


def test_chance_is_stable_but_unrelated_to_the_brief():
    index = search.build("chance", CORPUS)
    assert index.rank("a pianist", 3) == index.rank("a pianist", 3)  # same every run
    assert sorted(index.rank("a pianist", 3)) == [1, 2, 3]


def test_the_semantic_index_ranks_by_meaning_not_by_words(monkeypatch):
    """The claim the dependency is for: "someone who works underwater" shares no
    word with "deep sea diver" and still has to come first.

    Pinned to the local model cache. Loading from the hub made this fail about
    one run in three — a test that reaches the network is not measuring the
    ranking, it is measuring the network, and an intermittent failure is worse
    than none because it teaches you to re-run instead of to look.
    """
    pytest.importorskip("sentence_transformers")
    monkeypatch.setenv("HF_HUB_OFFLINE", "1")
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "1")
    from core import config
    from sentence_transformers import SentenceTransformer

    try:
        model = SentenceTransformer(config.EMBEDDING_MODEL)
    except Exception as exc:  # noqa: BLE001 — any hub or cache failure, not just one
        pytest.skip(f"{config.EMBEDDING_MODEL} is not in the local cache: {type(exc).__name__}")

    index = search.build("semantic", CORPUS, model)
    assert index.rank("someone who works underwater for a living", 3)[0] == 3
    assert search.build("lexical", CORPUS).rank(
        "someone who works underwater for a living", 3)[0] != 3, (
        "the lexical baseline solved it too, so this no longer tests meaning")


def test_the_corpus_holds_the_actors_the_queries_need():
    if not ACTORS.exists():
        pytest.skip("no actors.json; run `python -m eval.casting.run build`")
    built = json.loads(ACTORS.read_text(encoding="utf-8"))
    known = {int(a["actor_id"]) for a in built["actors"]}
    missing = [
        q["answer"]["name"] for q in _queries()["queries"] if q["answer"]["tmdb_id"] not in known
    ]
    assert not missing, f"no record for {missing}, so those briefs cannot be scored"
    assert built["corpus_size"] >= 200, (
        f"a corpus of {built['corpus_size']} makes recall@10 nearly free; chance alone scores "
        f"{metrics.chance_recall_at(10, built['corpus_size']):.0%}"
    )


# ----------------------------------------------- the swap this makes possible --


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def execute(self, *_a):
        pass

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _Cursor(self.rows)


def test_vectors_from_another_model_are_refused_not_searched():
    """384 is a common width — all-MiniLM-L6-v2 and bge-small-en-v1.5 both use
    it — so a swapped EMBEDDING_MODEL passes every dimension check and returns
    confident nonsense. `model_name` was recorded from the start and never read;
    this is what makes acting on the evaluation's result safe."""
    from core import config
    from services.casting_kb import matching

    matching._refuse_a_mismatched_model(_Connection([(config.EMBEDDING_MODEL,)]))
    matching._refuse_a_mismatched_model(_Connection([]))  # nothing stored yet

    with pytest.raises(RuntimeError, match="not comparable"):
        matching._refuse_a_mismatched_model(_Connection([("BAAI/bge-small-en-v1.5",)]))


def test_the_report_states_a_loss_as_a_loss():
    """The verdict could originally only say "no clear difference", so a
    baseline beating the shipped index would have been reported as a tie."""
    from eval.casting.run import _verdict

    beaten = {
        "indexes": {"semantic": {"recall@10": 0.19}, "lexical": {"recall@10": 0.35}},
        "chance_recall@10": 0.01,
        "contrasts": {"semantic vs lexical": {"gap": -0.15, "low": -0.29, "high": -0.02, "p": 0.99}},
    }
    assert "Word overlap beats the embedding" in _verdict(beaten)

    tied = {
        "indexes": {"semantic": {"recall@10": 0.33}, "lexical": {"recall@10": 0.35}},
        "chance_recall@10": 0.01,
        "contrasts": {"semantic vs lexical": {"gap": -0.02, "low": -0.17, "high": 0.13, "p": 0.65}},
    }
    assert "does not clearly beat" in _verdict(tied)
