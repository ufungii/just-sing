"""Guest + solo match flow against the real dev database (skipped without DATABASE_URL).
Cleans up the rows it creates."""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api.db import get_engine
from api.main import app
from api.seed import seed

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")

GOOD = {"phrases": [{"phrase_id": "p1", "rating": "great", "pitch": 80, "timing": 60, "coverage": 0.9}]}


@pytest.fixture
def guests():
    seed()
    ids = []
    yield ids
    with get_engine().begin() as c:
        for g in ids:
            c.execute(text("delete from turn_attempt where match_id in (select id from match where guest_id=:g)"), {"g": g})
            c.execute(text("delete from match_player where match_id in (select id from match where guest_id=:g)"), {"g": g})
            c.execute(text("delete from match where guest_id=:g"), {"g": g})
            c.execute(text("delete from guest_session where id=:g"), {"g": g})


def new_guest(guests, name="tester"):
    c = TestClient(app)
    guests.append(c.post("/api/guests", json={"display_name": name}).json()["id"])
    return c


def test_solo_flow(guests):
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    key = {"Idempotency-Key": "k1"}
    url = f"/api/turns/{m['attempt_id']}"

    assert c.post(f"{url}/result", json=GOOD, headers=key).status_code == 409  # not begun
    assert c.post(f"{url}/begin", json={"register": 0}).status_code == 200
    bad = {"phrases": [{**GOOD["phrases"][0], "phrase_id": "nope"}]}
    assert c.post(f"{url}/result", json=bad, headers=key).status_code == 422

    first = c.post(f"{url}/result", json=GOOD, headers=key)
    assert first.status_code == 200
    assert first.json()["total"] == 76.0  # exactly, not 76.00000000000001
    assert c.post(f"{url}/result", json=GOOD, headers=key).json() == first.json()  # replay
    assert c.post(f"{url}/result", json=GOOD, headers={"Idempotency-Key": "k2"}).status_code == 409

    assert c.get(f"/api/matches/{m['match_id']}").json()["state"] == "finished"
    assert c.get("/api/history").json()[0]["match_id"] == m["match_id"]
    r = c.post(f"/api/matches/{m['match_id']}/rematch").json()
    assert r["match_id"] != m["match_id"]


def test_other_guest_cannot_read(guests):
    a, b = new_guest(guests, "a"), new_guest(guests, "b")
    m = a.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    assert b.get(f"/api/matches/{m['match_id']}").status_code == 404
    assert TestClient(app).get("/api/history").status_code == 401  # no cookie


def play_turn(c, match_id, attempt_id, pitch):
    phrases = {"phrases": [{**GOOD["phrases"][0], "pitch": pitch, "timing": pitch}]}
    assert c.post(f"/api/turns/{attempt_id}/begin", json={}).status_code == 200
    r = c.post(f"/api/turns/{attempt_id}/result", json=phrases, headers={"Idempotency-Key": str(pitch)})
    assert r.status_code == 200 and r.json()["mode"] == "battle"
    return c.get(f"/api/matches/{match_id}").json()


def test_local_battle_alternates_and_picks_winner_or_tie(guests):
    c = new_guest(guests)
    for scores, winner in [((70, 90), 1), ((80, 80.04), None)]:  # second pair ties at 1 decimal
        m = c.post("/api/matches", json={"clip_id": "synthetic-demo", "players": ["Ann", "Bo"]}).json()
        view = c.get(f"/api/matches/{m['match_id']}").json()
        assert [p["display_name"] for p in view["players"]] == ["Ann", "Bo"] and len(view["attempts"]) == 1
        view = play_turn(c, m["match_id"], m["attempt_id"], scores[0])
        assert view["active_slot"] == 1 and view["state"] == "active" and view["winner_slot"] is None
        # slot 0 cannot go again; slot 1's attempt is now the open one
        assert c.post(f"/api/turns/{m['attempt_id']}/begin", json={}).status_code == 409
        second = next(a["id"] for a in view["attempts"] if a["slot"] == 1)
        view = play_turn(c, m["match_id"], second, scores[1])
        assert view["state"] == "finished" and view["winner_slot"] == winner
    rematch = c.post(f"/api/matches/{m['match_id']}/rematch").json()
    assert [p["display_name"] for p in c.get(f"/api/matches/{rematch['match_id']}").json()["players"]] == ["Ann", "Bo"]


def test_concurrent_submit_and_retry_never_crash_or_lose_a_result(guests):
    """Regression: submit locked attempt->match and retry locked match->attempt, so racing them could
    deadlock (500), or retry could invalidate a result that had just been accepted."""
    from concurrent.futures import ThreadPoolExecutor
    c = new_guest(guests)
    for i in range(6):
        m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
        a = m["attempt_id"]
        c.post(f"/api/turns/{a}/begin", json={})
        with ThreadPoolExecutor(2) as pool:
            fs = pool.submit(c.post, f"/api/turns/{a}/result", json=GOOD, headers={"Idempotency-Key": f"k{i}"})
            fr = pool.submit(c.post, f"/api/matches/{m['match_id']}/retry")
            rs, rr = fs.result(), fr.result()
        assert rs.status_code in (200, 409) and rr.status_code in (200, 409), (rs.text, rr.text)
        states = {x["id"]: x["state"] for x in c.get(f"/api/matches/{m['match_id']}").json()["attempts"]}
        if rs.status_code == 200:
            assert states[a] == "accepted"  # an accepted result is never invalidated afterwards


def test_history_has_one_row_per_match(guests):
    """Regression: history returned every accepted attempt, so one local battle showed up as two rows
    with both players' totals and nothing saying whose was whose."""
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo", "players": ["Ann", "Bo"]}).json()
    view = play_turn(c, m["match_id"], m["attempt_id"], 70)
    play_turn(c, m["match_id"], next(a["id"] for a in view["attempts"] if a["slot"] == 1), 90)
    solo = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    c.post(f"/api/turns/{solo['attempt_id']}/begin", json={})
    c.post(f"/api/turns/{solo['attempt_id']}/result", json=GOOD, headers={"Idempotency-Key": "s"})

    rows = c.get("/api/history").json()
    assert [r["match_id"] for r in rows].count(m["match_id"]) == 1
    battle = next(r for r in rows if r["match_id"] == m["match_id"])
    assert battle["total"] is None and [(p["display_name"], p["total"]) for p in battle["players"]] == [("Ann", 70), ("Bo", 90)]
    assert next(r for r in rows if r["match_id"] == solo["match_id"])["total"] == 76.0


def test_turn_deadline_holds(guests):
    """Regression: a second /begin reset the deadline and register (so a turn could be kept alive
    forever), and a result after the deadline was accepted until the 15 s recovery tick ran."""
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    a = m["attempt_id"]
    deadline = lambda: get_engine().connect().execute(text("select deadline_at from turn_attempt where id=:i"), {"i": a}).scalar()
    c.post(f"/api/turns/{a}/begin", json={"register": 0})
    first = deadline()
    assert c.post(f"/api/turns/{a}/begin", json={"register": 0}).status_code == 200  # a harmless repeat
    assert deadline() == first
    assert c.post(f"/api/turns/{a}/begin", json={"register": 12}).json()["error"]["code"] == "attempt_already_started"

    with get_engine().begin() as conn:
        conn.execute(text("update turn_attempt set deadline_at = now() - interval '1 second' where id=:i"), {"i": a})
    late = c.post(f"/api/turns/{a}/result", json=GOOD, headers={"Idempotency-Key": "late"})
    assert late.json()["error"]["code"] == "attempt_invalidated"
    assert c.get(f"/api/matches/{m['match_id']}").json()["state"] == "retry_required"


def test_turns_refuse_a_changed_clip_version(guests, monkeypatch):
    """Regression: begin/submit used the current manifest, not the match's frozen clip_version, so a
    manifest update mid-match graded results against the wrong phrases and durations."""
    from api import play as play_module
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    c.post(f"/api/turns/{m['attempt_id']}/begin", json={})
    bumped = play_module.CATALOG["synthetic-demo"].model_copy(update={"version": 2})
    monkeypatch.setitem(play_module.CATALOG, "synthetic-demo", bumped)
    r = c.post(f"/api/turns/{m['attempt_id']}/result", json=GOOD, headers={"Idempotency-Key": "v"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "clip_version_changed"
    fresh = c.post("/api/matches", json={"clip_id": "synthetic-demo"})
    assert fresh.json()["error"]["code"] == "catalog_not_seeded"  # version 2 was never seeded


def test_engine_scoring_null_timing_and_server_side_ratings(guests):
    """The server recomputes score and rating; the client cannot choose them. timing=null is scored on pitch alone."""
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    url = f"/api/turns/{m['attempt_id']}"
    c.post(f"{url}/begin", json={})
    cheat = {"phrases": [{"phrase_id": "p1", "rating": "perfect", "score": 100, "pitch": 40, "timing": None, "coverage": 0.9}]}
    r = c.post(f"{url}/result", json=cheat, headers={"Idempotency-Key": "n"})
    assert r.status_code == 200
    ph = r.json()["phrases"][0]
    assert ph == {"phrase_id": "p1", "pitch": 40.0, "timing": None, "score": 40.0, "coverage": 0.9, "rating": "bad"}
    assert r.json()["total"] == 40.0
    assert c.get(f"/api/matches/{m['match_id']}").json()["attempts"][0]["score"]["phrases"][0]["timing"] is None


def test_out_of_range_and_unscoreable_clip_are_422_invalid_result(guests, monkeypatch):
    from api import play as play_module
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    url = f"/api/turns/{m['attempt_id']}"
    c.post(f"{url}/begin", json={})
    # the model's own 0-100 bounds catch this first (standard validation error)
    assert c.post(f"{url}/result", json={"phrases": [{**GOOD["phrases"][0], "pitch": 120}]},
                  headers={"Idempotency-Key": "r"}).status_code == 422
    # a clip with nothing scoreable is a manifest problem: the engine's ValueError becomes invalid_result
    monkeypatch.setitem(play_module._weight_cache, ("synthetic-demo", 1), [0])
    r = c.post(f"{url}/result", json=GOOD, headers={"Idempotency-Key": "z"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_result"


def test_old_rows_without_score_still_read(guests):
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    url = f"/api/turns/{m['attempt_id']}"
    c.post(f"{url}/begin", json={})
    assert c.post(f"{url}/result", json=GOOD, headers={"Idempotency-Key": "o"}).status_code == 200
    with get_engine().begin() as conn:  # simulate a row saved by the stand-in
        conn.execute(text("update turn_attempt set phrase_results = cast(:j as jsonb) where id=:i"),
                     {"i": m["attempt_id"], "j": '[{"phrase_id":"p1","rating":"great","pitch":80,"timing":60,"coverage":0.9}]'})
    ph = c.get(f"/api/matches/{m['match_id']}").json()["attempts"][0]["score"]["phrases"][0]
    assert ph["score"] == 80 and ph["timing"] == 60
    assert c.get("/api/history").status_code == 200


def four_phrase_clip(monkeypatch):
    """synthetic-demo with 4 phrases of 5 s each (clip duration 20 s) and equal weights."""
    from api import play as play_module
    from api.models import Phrase
    song = play_module.CATALOG["synthetic-demo"]
    four = song.model_copy(update={"duration": 20.0, "phrases": [
        Phrase(id=f"q{i}", line_index=0, start=5.0 * i, end=5.0 * i + 5.0) for i in range(4)]})
    monkeypatch.setitem(play_module.CATALOG, "synthetic-demo", four)
    monkeypatch.setitem(play_module._weight_cache, ("synthetic-demo", 1), [10, 10, 10, 10])


def ph(*ids, pitch=80):
    return {"phrases": [{"phrase_id": i, "pitch": pitch, "timing": pitch, "coverage": 1} for i in ids]}


def test_practice_range_scores_only_included_phrases(guests, monkeypatch):
    four_phrase_clip(monkeypatch)
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    url = f"/api/turns/{m['attempt_id']}"
    for bad in ({"start": 7, "end": 7}, {"start": 0, "end": 25}, {"start": 1, "end": 4}, {"start": -1, "end": 5}):
        r = c.post(f"{url}/begin", json={"range": bad})
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_range", bad
    # ragged edges snap to phrases q1-q2: 4.97..15.02 holds [5,10] and [10,15] fully
    assert c.post(f"{url}/begin", json={"range": {"start": 4.97, "end": 15.02}}).status_code == 200
    assert c.post(f"{url}/begin", json={"range": {"start": 5, "end": 15}}).status_code == 200  # same normalized range
    assert c.post(f"{url}/begin", json={}).status_code == 409  # not changeable once started
    key = {"Idempotency-Key": "r1"}
    for wrong in (ph("q0", "q1", "q2", "q3"), ph("q1"), ph("q1", "q2", "q3")):
        assert c.post(f"{url}/result", json=wrong, headers=key).status_code == 422
    body = {"phrases": [*ph("q1", pitch=100)["phrases"], *ph("q2", pitch=50)["phrases"]]}
    r = c.post(f"{url}/result", json=body, headers=key)
    assert r.status_code == 200
    assert r.json()["range"] == {"start": 5.0, "end": 15.0} and r.json()["pitch"] == 75.0
    assert c.post(f"{url}/result", json=body, headers=key).json() == r.json()  # replay
    got = c.get(f"/api/matches/{m['match_id']}").json()["attempts"][0]["score"]
    assert got["range"] == {"start": 5.0, "end": 15.0}
    assert c.get("/api/history").json()[0]["range"] == {"start": 5.0, "end": 15.0}


def test_full_clip_has_null_range_and_battle_rejects_range(guests, monkeypatch):
    four_phrase_clip(monkeypatch)
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    url = f"/api/turns/{m['attempt_id']}"
    c.post(f"{url}/begin", json={})
    r = c.post(f"{url}/result", json=ph("q0", "q1", "q2", "q3"), headers={"Idempotency-Key": "f"})
    assert r.status_code == 200 and r.json()["range"] is None
    assert c.get("/api/history").json()[0]["range"] is None
    b = c.post("/api/matches", json={"clip_id": "synthetic-demo", "players": ["a", "b"]}).json()
    r = c.post(f"/api/turns/{b['attempt_id']}/begin", json={"range": {"start": 0, "end": 5}})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_range"


def test_practice_runs_stay_off_the_leaderboard(guests, monkeypatch):
    four_phrase_clip(monkeypatch)
    from api import play as play_module
    c = new_guest(guests)
    with get_engine().begin() as conn:  # leaderboard only ranks logged-in accounts
        conn.execute(text("update guest_session set auth0_sub=:s where id=:g"),
                     {"s": f"test|{guests[-1]}", "g": guests[-1]})
    def lb():
        return [r for r in c.get("/api/leaderboard", params={"clip_id": "synthetic-demo"}).json() if r["display_name"] == "tester"]
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    c.post(f"/api/turns/{m['attempt_id']}/begin", json={"range": {"start": 0, "end": 10}})
    assert c.post(f"/api/turns/{m['attempt_id']}/result", json=ph("q0", "q1"), headers={"Idempotency-Key": "p"}).status_code == 200
    assert lb() == []
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    c.post(f"/api/turns/{m['attempt_id']}/begin", json={})
    c.post(f"/api/turns/{m['attempt_id']}/result", json=ph("q0", "q1", "q2", "q3", pitch=60), headers={"Idempotency-Key": "q"})
    assert lb() == [{"display_name": "tester", "total": 60.0}]


def test_old_rows_read_range_null(guests):
    c = new_guest(guests)
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    c.post(f"/api/turns/{m['attempt_id']}/begin", json={})
    c.post(f"/api/turns/{m['attempt_id']}/result", json=GOOD, headers={"Idempotency-Key": "o"})
    assert c.get(f"/api/matches/{m['match_id']}").json()["attempts"][0]["score"]["range"] is None


def test_guided_runs_are_flagged_and_stay_off_the_leaderboard(guests):
    c = new_guest(guests)
    with get_engine().begin() as conn:  # leaderboard only ranks logged-in accounts
        conn.execute(text("update guest_session set auth0_sub=:s where id=:g"),
                     {"s": f"test|{guests[-1]}", "g": guests[-1]})
    lb = lambda: [r for r in c.get("/api/leaderboard", params={"clip_id": "synthetic-demo"}).json() if r["display_name"] == "tester"]

    def run(key, guided):
        m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
        c.post(f"/api/turns/{m['attempt_id']}/begin", json={})
        body = {**GOOD, **({"guide_used": True} if guided else {})}
        r = c.post(f"/api/turns/{m['attempt_id']}/result", json=body, headers={"Idempotency-Key": key})
        return m, r.json()

    m, score = run("g", True)
    assert score["guided"] is True and lb() == []
    assert c.get(f"/api/matches/{m['match_id']}").json()["attempts"][0]["score"]["guided"] is True
    assert c.get("/api/history").json()[0]["guided"] is True
    _, score = run("u", False)  # guide_used omitted = false
    assert score["guided"] is False and len(lb()) == 1
    assert c.get("/api/history").json()[0]["guided"] is False
