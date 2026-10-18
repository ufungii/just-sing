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


def test_login_and_claim():
    c = TestClient(app)
    c.post("/api/guests", json={"display_name": "claimme"})
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    c.post(f"/api/turns/{m['attempt_id']}/begin", json={})
    c.post(f"/api/turns/{m['attempt_id']}/result", json=GOOD, headers={"Idempotency-Key": "k"})

    auth_h = {"Authorization": f"Bearer {token('test|42')}"}
    assert c.get("/api/history", headers=auth_h).json() == []  # new account starts empty
    assert c.post("/api/auth/claim", headers=auth_h).json()["claimed_guest_history"] is True
    assert c.get("/api/history", headers=auth_h).json()[0]["match_id"] == m["match_id"]


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


def test_claim_carries_the_guest_name_to_the_account():
    """Regression: accounts were created as 'Player' and claim never copied the guest's chosen name,
    so every saved account read 'Player'."""
    c = TestClient(app)
    c.post("/api/guests", json={"display_name": "claimme"})
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    play(c, {}, m["attempt_id"], 61)
    h = {"Authorization": f"Bearer {token('test|named')}"}
    c.post("/api/auth/claim", headers=h)
    with get_engine().begin() as conn:
        name = conn.execute(text("select display_name from guest_session where auth0_sub='test|named'")).scalar_one()
    assert name == "claimme"


def test_online_room_as_bearer_account_with_websocket_and_retry():
    """Regression: an account (bearer token) must be a room member over HTTP and the WebSocket, and the
    lost-turn retry must work for it."""
    from api.retention import reconcile_attempts
    acct = {"Authorization": f"Bearer {token('test|room1')}"}
    with TestClient(app) as c:  # entering the context starts the loop used for broadcasts
        room = c.post("/api/rooms", json={"clip_id": "synthetic-demo"}, headers=acct).json()
        other = TestClient(app)
        other.post("/api/guests", json={"display_name": "claimme"})
        assert other.post("/api/rooms/join", json={"code": room["code"]}).status_code == 200
        for cl, h in ((c, acct), (other, {})):
            assert cl.post(f"/api/rooms/{room['id']}/ready", json={"ready": True}, headers=h).status_code == 200
        start = c.post(f"/api/rooms/{room['id']}/start", headers=acct).json()
        a = start["attempt_id"]

        # the socket accepts the token as a subprotocol, and refuses a bad one or none
        with c.websocket_connect(f"/ws/rooms/{room['id']}", subprotocols=["bearer", token("test|room1")]) as ws:
            assert ws.receive_json()["type"] == "room_snapshot"
        with pytest.raises(Exception):
            with c.websocket_connect(f"/ws/rooms/{room['id']}", subprotocols=["bearer", "garbage"]):
                pass

        assert c.post(f"/api/turns/{a}/begin", json={}, headers=acct).status_code == 200
        with get_engine().begin() as conn:  # the singer left and the deadline passed
            conn.execute(text("update turn_attempt set deadline_at = now() - interval '1 second' where id=:i"), {"i": a})
        assert reconcile_attempts() >= 1
        assert c.get(f"/api/rooms/{room['id']}", headers=acct).json()["match"]["state"] == "retry_required"
        assert other.post(f"/api/matches/{start['match_id']}/retry").status_code == 403  # not their seat
        new = c.post(f"/api/matches/{start['match_id']}/retry", headers=acct).json()["attempt_id"]
        c.post(f"/api/turns/{new}/begin", json={}, headers=acct)
        r = c.post(f"/api/turns/{new}/result", json=GOOD, headers={**acct, "Idempotency-Key": "k"})
        assert r.status_code == 200
