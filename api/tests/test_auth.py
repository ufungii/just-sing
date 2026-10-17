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
        for t in ("turn_attempt", "match_player"):
            c.execute(text(f"delete from {t} where match_id in (select id from match where guest_id in {ids})"))
        c.execute(text(f"delete from match where guest_id in {ids}"))
        c.execute(text(f"delete from guest_session where id in {ids}"))


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
