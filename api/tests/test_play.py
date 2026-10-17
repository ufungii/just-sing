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
