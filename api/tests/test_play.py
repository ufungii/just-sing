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
    assert first.json()["total"] == pytest.approx(0.8 * 80 + 0.2 * 60)
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
