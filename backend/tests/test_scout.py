"""The talent scout, all on free plans: Tavily finds pages, Gemini's free
tier reads them and may suggest only people they name, and TMDb adds a face and
credits. With no live source the offline demo cast stands in, labelled."""
import pytest

from core import config
from core.orchestrator.state import GlobalState
from domains.casting.agents import agent_scout
from services import gemini_client, tavily_client
from services.casting_kb import tmdb

ROLES = {"ROLE_LEAD": {"name": "Mara Voss", "description": "ex-detective, 30s", "type": "lead"},
         "ROLE_ANTAG": {"name": "Silas Kade", "description": "deepfake broker, 40s", "type": "antagonist"}}
PAGES = [
    {"title": "Atlanta actors to watch", "url": "https://example.org/watch",
     "content": "Stage favourite Ana Ruíz has a new series; Tom Park signed with Peach State Talent, "
                "and Adetokumboh M'Cormack joins the cast."},
    {"title": "Peach State Talent roster", "url": "https://example.org/roster",
     "content": "Our roster: Tom Park, Dee Walsh, Artemis."},
]


def _state():
    return GlobalState(project_id="PROJ_T", locality="Atlanta, GA", director_notes="Night shoots",
                       role_requirements=ROLES)


@pytest.fixture
def live(monkeypatch):
    """A free key and Tavily; each test sets the model's reply."""
    searches = []
    monkeypatch.setattr(config, "has_gemini", lambda: True)
    monkeypatch.setattr(config, "has_tavily", lambda: True)

    def search(query, max_results=4):
        searches.append(query)
        return {"results": PAGES}

    monkeypatch.setattr(tavily_client, "search", search)

    def answer(rows):
        monkeypatch.setattr(gemini_client, "generate_json_traced",
                            lambda prompt, **kwargs: ({"candidates": rows}, {"source": "gemini", "model": "flash"}))

    answer.searches = searches
    return answer


def test_the_free_path_keeps_only_people_the_results_name(live, monkeypatch):
    live([
        {"name": "Ana Ruiz", "role_id": "ROLE_LEAD", "source": 1, "media_url": "https://example.org/watch",
         "metadata": {"quote_usd": 18000, "followers": None, "agency": "", "recent_press": "New series."}},
        {"name": "Invented Person", "role_id": "ROLE_LEAD", "source": 1, "metadata": {}},
        {"name": "Dee Wal", "role_id": "ROLE_LEAD", "source": 2, "metadata": {}},
        {"name": "Artemis", "role_id": "ROLE_LEAD", "source": 2, "metadata": {}},
        {"name": "Adetokumboh M\u2019Cormack", "role_id": "ROLE_ANTAG", "source": 1, "metadata": {}},
        {"name": "Tom Park", "role_id": "ROLE_ANTAG", "source": 7, "media_url": "https://video.example/invented",
         "metadata": {"agency": "Peach State Talent"}},
        {"name": "Dee Walsh (actress)", "role_id": "ROLE_LEAD", "source": 2, "metadata": {}},
    ])
    state = _state()
    found = agent_scout.scout_candidates(state)

    assert [c.name for c in found] == ["Ana Ruiz", "Adetokumboh M\u2019Cormack", "Tom Park", "Dee Walsh"], (
        "unnamed, half-named and first-name-only people are dropped; a curly apostrophe still matches")
    ana, _, tom, dee = found
    assert dee.metadata["source_url"] == "https://example.org/roster", "a note in brackets is not part of the name"
    assert ana.media_url == "https://example.org/watch"
    assert "invented" not in tom.media_url, "a reel link the results do not give is dropped"
    assert ana.metadata["source_url"] == "https://example.org/watch", "accents do not stop the match"
    assert tom.metadata["source_url"] == "https://example.org/watch", "a bad citation falls back to a real one"
    assert ana.metadata["is_live_scouted"] and ana.metadata["quote_is_estimate"]
    assert ana.metadata["followers_estimated"] and ana.metadata["followers"] == agent_scout.NEUTRAL_FOLLOWERS
    assert ana.metadata["agency"] == "" and tom.metadata["agency"] == "Peach State Talent"
    assert "reading web results from Tavily" in ana.metadata["scouted_via"]
    assert len(live.searches) == 2, "two searches, one free-plan credit each"
    assert all("Atlanta" in q and "Night shoots" not in q for q in live.searches), (
        "searches look for local actors; the director's notes go to the model, where genre words cannot "
        "pull in articles about famous films")
    ingested = [e["payload"] for e in state.event_log if e["intent"] == "candidate_ingested"]
    assert {p["source"] for p in ingested} == {"live_web_results"}


def test_tmdb_adds_faces_and_credits_to_live_names_only(live, monkeypatch):
    monkeypatch.setattr(config, "has_tmdb", lambda: True)
    profile = {"tmdb_id": 7, "tmdb_url": "https://www.themoviedb.org/person/7",
               "headshot_url": "https://image.tmdb.org/t/p/w342/ana.jpg",
               "credits": [{"title": "Night Fare", "year": "2023", "kind": "Film"}]}
    looked_up = []

    def profile_for(name):
        looked_up.append(name)
        if name == "Tom Park":
            raise RuntimeError("TMDb is down")
        return profile if name == "Ana Ruiz" else None

    monkeypatch.setattr(tmdb, "profile_for", profile_for)
    live([{"name": "Ana Ruiz", "role_id": "ROLE_LEAD"}, {"name": "Tom Park", "role_id": "ROLE_ANTAG"},
          {"name": "Dee Walsh", "role_id": "ROLE_LEAD"}])
    ana, tom, dee = agent_scout.scout_candidates(_state())

    assert ana.metadata["headshot_url"].endswith("/ana.jpg") and ana.metadata["credits"][0]["title"] == "Night Fare"
    assert ana.metadata["tmdb_match"] == "name"
    assert "tmdb_match" not in tom.metadata, "a failed lookup leaves the candidate as it was"
    assert dee.metadata["tmdb_match"] == "none"

    # The offline cast is made up: it must never borrow a real person's face.
    looked_up.clear()
    monkeypatch.setattr(config, "has_tavily", lambda: False)
    offline_cast = agent_scout.scout_candidates(_state())
    assert looked_up == [] and not any(c.metadata.get("headshot_url") for c in offline_cast)


def test_no_web_results_means_the_labelled_offline_cast(monkeypatch):
    monkeypatch.setattr(config, "has_gemini", lambda: True)
    found = agent_scout.scout_candidates(_state())
    assert {c.name for c in found} >= {"Lucia Morales", "Darius Thorne"}
    assert all(not c.metadata["is_live_scouted"] for c in found)
    assert "TAVILY_API_KEY" in found[0].metadata["scouted_via"]

    # With a key but nothing back (the free plan's searches used up), the
    # label says so instead of asking for a key that is already set.
    monkeypatch.setattr(config, "has_tavily", lambda: True)
    monkeypatch.setattr(tavily_client, "search", lambda query, max_results=4: {
        "results": [], "error": "HTTPError: HTTP Error 432: plan limit exceeded"})
    found = agent_scout.scout_candidates(_state())
    assert all(not c.metadata["is_live_scouted"] for c in found)
    label = found[0].metadata["scouted_via"]
    assert "used up" in label and "TAVILY_API_KEY" not in label


def test_results_that_name_nobody_fall_back_to_the_offline_cast(live):
    live([{"name": "Made Up", "role_id": "ROLE_LEAD"}])
    found = agent_scout.scout_candidates(_state())
    assert all(not c.metadata["is_live_scouted"] for c in found)
    assert "named nobody suitable" in found[0].metadata["scouted_via"]


@pytest.mark.parametrize("written, fee", [
    (20000, 20000), ("$20,000", 20000), ("20k", 20000), ("$15,000-25,000", 20000),
    ("15–20k", 17500), ("$1.5M", 1_500_000), ("unknown", None), (None, None), (0, None), (True, None),
])
def test_fees_written_as_text_are_read(written, fee):
    assert agent_scout._fee(written) == fee


def test_names_in_scripts_without_spaces_still_match():
    page = [{"title": "キャスト", "url": "https://example.jp/cast", "content": "主演は山田太郎が務める。"}]
    kept = agent_scout._named_in_results([{"name": "山田太郎"}, {"name": "田中花子"}], page)
    assert [row["name"] for row in kept] == ["山田太郎"]
    assert kept[0]["source_url"] == "https://example.jp/cast"


def test_the_tmdb_profile_is_an_exact_acting_match(monkeypatch):
    monkeypatch.setattr(config, "TMDB_API_KEY", "key")
    people = [
        {"id": 1, "name": "Ana Ruiz", "known_for_department": "Directing", "popularity": 90},
        {"id": 2, "name": "ana  ruiz", "known_for_department": "Acting", "popularity": 3,
         "profile_path": "/a.jpg",
         "known_for": [{"media_type": "movie", "title": "Night Fare", "release_date": "2023-05-01"},
                       {"media_type": "tv", "name": "Harbor", "first_air_date": "2021-01-01"}]},
        {"id": 3, "name": "Ana Ruiz-Soto", "known_for_department": "Acting", "popularity": 50},
    ]
    seen = {}

    class Reply:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": people}

    def get(url, params, timeout):
        seen.update(params, url=url)
        return Reply()

    monkeypatch.setattr(tmdb.requests, "get", get)
    profile = tmdb.profile_for("Ana Ruiz")
    assert seen["url"].endswith("/search/person") and seen["query"] == "Ana Ruiz"
    assert profile["tmdb_id"] == 2 and profile["headshot_url"] == "https://image.tmdb.org/t/p/w342/a.jpg"
    assert profile["credits"] == [{"title": "Night Fare", "year": "2023", "kind": "Film"},
                                  {"title": "Harbor", "year": "2021", "kind": "Series"}]
    assert tmdb.profile_for("Ana Ruíz")["tmdb_id"] == 2, "accents aside, it is the same name"
    people.append({"id": 4, "name": "Ana Ruiz", "known_for_department": "Acting", "popularity": 70})
    assert tmdb.profile_for("Ana Ruiz") is None, "two actors share the name, so neither is picked"
    people[:] = [people[0]]
    assert tmdb.profile_for("Ana Ruiz") is None, "a director of the same name is not an actor match"


def test_tmdb_retries_on_its_alias_host_when_a_server_drops_the_connection(monkeypatch):
    monkeypatch.setattr(config, "TMDB_API_KEY", "key")
    hosts = []

    class Reply:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"id": 9, "name": "Tom Park", "known_for_department": "Acting"}]}

    def get(url, params, timeout):
        hosts.append(url.split("/")[2])
        if "themoviedb" in url:
            raise tmdb.requests.exceptions.SSLError("EOF occurred in violation of protocol")
        return Reply()

    monkeypatch.setattr(tmdb.requests, "get", get)
    assert tmdb.profile_for("Tom Park")["tmdb_id"] == 9
    assert hosts == ["api.themoviedb.org", "api.tmdb.org"]
