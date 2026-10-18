"""The in-memory limiter behind POST /api/guests and room joins. No database needed: the limit trips before any query."""
from fastapi.testclient import TestClient

from api import play
from api.main import app


def test_too_many_allows_up_to_the_limit_then_refuses():
    play._hits.clear()
    assert [play.too_many("t", "1.2.3.4", 2) for _ in range(3)] == [False, False, True]
    assert play.too_many("t", "5.6.7.8", 2) is False  # another address has its own budget


def test_guest_creation_is_limited_per_address(monkeypatch):
    play._hits.clear()
    monkeypatch.setattr(play, "GUESTS_PER_MINUTE_PER_IP", 0)
    r = TestClient(app).post("/api/guests", json={"display_name": "bot"})
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_guests"
