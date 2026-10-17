"""Auth0 flow with a locally generated key standing in for Auth0's (real login is untested)."""
import os

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import text

from api import auth
from api.db import get_engine
from api.main import app
from api.retention import cleanup_expired
from api.seed import seed
from api.tests.test_play import GOOD

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
DOMAIN, AUD = "test.example.auth0.com", "https://api.test"


def token(sub, aud=AUD, exp=3600):
    import time
    return jwt.encode({"sub": sub, "aud": aud, "iss": f"https://{DOMAIN}/", "exp": time.time() + exp},
                      KEY, algorithm="RS256")


@pytest.fixture(autouse=True)
def auth0(monkeypatch):
    monkeypatch.setenv("AUTH0_DOMAIN", DOMAIN)
    monkeypatch.setenv("AUTH0_AUDIENCE", AUD)
    monkeypatch.setattr(auth, "signing_key", lambda t: KEY.public_key())
    seed()
    yield
    with get_engine().begin() as c:
        ids = "(select id from guest_session where auth0_sub like 'test|%' or display_name='claimme')"
        rooms = f"(select id from room where host_guest_id in {ids})"
        m = f"(select id from match where guest_id in {ids} or room_id in {rooms})"
        for sql in (f"delete from turn_attempt where match_id in {m}", f"delete from match_player where match_id in {m}",
                    f"delete from match where id in {m}", f"delete from room_member where room_id in {rooms} or guest_id in {ids}",
                    f"delete from room where id in {rooms}", f"delete from guest_session where id in {ids}"):
            c.execute(text(sql))


def test_bad_tokens_rejected():
    c = TestClient(app)
    for t in (token("test|1", aud="https://other"), token("test|1", exp=-10), "garbage"):
        r = c.get("/api/history", headers={"Authorization": f"Bearer {t}"})
        assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_token"


def test_login_claim_and_leaderboard():
    c = TestClient(app)
    c.post("/api/guests", json={"display_name": "claimme"})
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    c.post(f"/api/turns/{m['attempt_id']}/begin", json={})
    c.post(f"/api/turns/{m['attempt_id']}/result", json=GOOD, headers={"Idempotency-Key": "k"})

    auth_h = {"Authorization": f"Bearer {token('test|42')}"}
    assert c.get("/api/history", headers=auth_h).json() == []  # new account starts empty
    assert c.post("/api/auth/claim", headers=auth_h).json()["claimed_guest_history"] is True
    assert c.get("/api/history", headers=auth_h).json()[0]["match_id"] == m["match_id"]
    assert [r["total"] for r in c.get("/api/leaderboard?clip_id=synthetic-demo").json()][:1] == [pytest.approx(76)]


def test_claim_moves_rooms_so_cleanup_keeps_working():
    """Regression: claim moved matches but not rooms, so the hourly cleanup hit a foreign-key error
    deleting the spent guest's room (and failed every hour after), and the account lost the room."""
    host, other = TestClient(app), TestClient(app)
    for c in (host, other):
        c.post("/api/guests", json={"display_name": "claimme"})
    room = host.post("/api/rooms", json={"clip_id": "synthetic-demo"}).json()
    other.post("/api/rooms/join", json={"code": room["code"]})
    for c in (host, other):
        c.post(f"/api/rooms/{room['id']}/ready", json={"ready": True})
    assert host.post(f"/api/rooms/{room['id']}/start").status_code == 200

    auth_h = {"Authorization": f"Bearer {token('test|77')}"}
    assert host.post("/api/auth/claim", headers=auth_h).json()["claimed_guest_history"] is True
    cleanup_expired()  # must not raise
    assert host.get(f"/api/rooms/{room['id']}", headers=auth_h).status_code == 200  # the account keeps the room


def test_parallel_first_requests_create_one_account():
    """Regression: find-then-insert with no unique constraint let parallel first requests after login
    create several accounts for one Auth0 user (reproduced: 7 of 8 users duplicated), splitting history."""
    from concurrent.futures import ThreadPoolExecutor
    for i in range(4):
        sub = f"test|race{i}"
        h = {"Authorization": f"Bearer {token(sub)}"}
        with ThreadPoolExecutor(8) as pool:
            codes = list(pool.map(lambda _: TestClient(app).get("/api/history", headers=h).status_code, range(8)))
        assert codes == [200] * 8
        with get_engine().connect() as c:
            assert c.execute(text("select count(*) from guest_session where auth0_sub=:s"), {"s": sub}).scalar() == 1


def play(c, h, attempt_id, score):
    c.post(f"/api/turns/{attempt_id}/begin", json={}, headers=h)
    body = {"phrases": [{**GOOD["phrases"][0], "pitch": score, "timing": score}]}
    return c.post(f"/api/turns/{attempt_id}/result", json=body, headers={**h, "Idempotency-Key": str(score)})


def test_leaderboard_counts_only_own_solo_scores_on_current_version(monkeypatch):
    """Regression: every accepted attempt in a no-room match was credited to the match owner, so a
    friend's local-battle score ranked under the owner's name; old clip versions were mixed in too."""
    from api import play as play_module
    c, h = TestClient(app), {"Authorization": f"Bearer {token('test|lb')}"}
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo", "players": ["me", "friend"]}, headers=h).json()
    play(c, h, m["attempt_id"], 40)
    second = next(a["id"] for a in c.get(f"/api/matches/{m['match_id']}", headers=h).json()["attempts"] if a["slot"] == 1)
    play(c, h, second, 95)  # the friend's score
    solo = c.post("/api/matches", json={"clip_id": "synthetic-demo"}, headers=h).json()
    play(c, h, solo["attempt_id"], 50)

    totals = [r["total"] for r in c.get("/api/leaderboard?clip_id=synthetic-demo").json()]
    assert 95 not in totals and 50 in totals

    bumped = play_module.CATALOG["synthetic-demo"].model_copy(update={"version": 2})
    monkeypatch.setitem(play_module.CATALOG, "synthetic-demo", bumped)
    assert 50 not in [r["total"] for r in c.get("/api/leaderboard?clip_id=synthetic-demo").json()]
