"""Coaching blurb with Gemini mocked: caching, failure handling, and that scoring is never touched."""
import os

import pytest

from api import coach
from api.tests.test_play import GOOD, guests, new_guest  # noqa: F401  (guests is a fixture)

needs_db = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")

SCORE = {"total": 76, "pitch": 80, "timing": 60, "register": 12,
         "phrases": [{"rating": "great", "pitch": 90, "timing": 80, "coverage": 1.0},
                     {"rating": "bad", "pitch": 40, "timing": 30, "coverage": 0.5}]}


def test_prompt_contains_only_measured_numbers():
    p = coach.build_prompt(SCORE, 2)
    assert "one octave higher" in p and "overall 76, pitch 80, timing 60" in p
    assert "phrase 2 of 2: rating bad, pitch 40/100, timing 30/100, sang 50% of it" in p
    assert "do not invent" in p


def finished_attempt(c):
    m = c.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    a = m["attempt_id"]
    c.post(f"/api/turns/{a}/begin", json={})
    c.post(f"/api/turns/{a}/result", json=GOOD, headers={"Idempotency-Key": "k"})
    return m["match_id"], a


@needs_db
def test_coach_flow(guests, monkeypatch):  # noqa: F811
    c = new_guest(guests)
    mid, a = finished_attempt(c)
    calls = []

    def fake(prompt):
        calls.append(prompt)
        return "  Nice   work!\n Tighten the timing.  " + "x" * 600

    monkeypatch.setattr(coach, "_generate", fake)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    before = c.get(f"/api/matches/{mid}").json()["attempts"][0]["score"]

    r = c.post(f"/api/turns/{a}/coach").json()
    assert r["status"] == "ok" and r["coach_blurb"].startswith("Nice work! Tighten the timing.")
    assert len(r["coach_blurb"]) == coach.MAX_BLURB_CHARS
    assert c.post(f"/api/turns/{a}/coach").json() == r and len(calls) == 1  # cached, no second call

    after = c.get(f"/api/matches/{mid}").json()["attempts"][0]["score"]
    assert after["coach_blurb"] == r["coach_blurb"]
    assert {k: v for k, v in after.items() if k != "coach_blurb"} == {k: v for k, v in before.items() if k != "coach_blurb"}


@needs_db
def test_failures_are_unavailable_and_retryable(guests, monkeypatch):  # noqa: F811
    c = new_guest(guests)
    mid, a = finished_attempt(c)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert c.post(f"/api/turns/{a}/coach").json() == {"status": "unavailable", "coach_blurb": None}

    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(coach, "_generate", lambda p: (_ for _ in ()).throw(RuntimeError("quota")))
    assert c.post(f"/api/turns/{a}/coach").json() == {"status": "unavailable", "coach_blurb": None}
    monkeypatch.setattr(coach, "_generate", lambda p: "   ")
    assert c.post(f"/api/turns/{a}/coach").json()["status"] == "unavailable"  # empty text is not a blurb
    assert c.get(f"/api/matches/{mid}").json()["attempts"][0]["score"]["coach_blurb"] is None  # nothing saved

    monkeypatch.setattr(coach, "_generate", lambda p: "Back online.")
    assert c.post(f"/api/turns/{a}/coach").json()["coach_blurb"] == "Back online."


@needs_db
def test_coach_guards(guests, monkeypatch):  # noqa: F811
    a_client, b_client = new_guest(guests, "a"), new_guest(guests, "b")
    m = a_client.post("/api/matches", json={"clip_id": "synthetic-demo"}).json()
    assert a_client.post(f"/api/turns/{m['attempt_id']}/coach").json()["error"]["code"] == "attempt_not_scored"
    assert b_client.post(f"/api/turns/{m['attempt_id']}/coach").status_code == 404  # not their match


@needs_db
def test_coach_does_not_hold_a_database_connection_during_the_gemini_call(guests, monkeypatch):  # noqa: F811
    """Regression: the request's session kept its connection checked out for the whole 10 s Gemini call,
    so a few slow blurbs could exhaust the small connection pool."""
    from api.db import get_engine
    c = new_guest(guests)
    mid, a = finished_attempt(c)
    seen = []
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setattr(coach, "_generate", lambda p: seen.append(get_engine().pool.checkedout()) or "Nice work.")
    assert c.post(f"/api/turns/{a}/coach").json()["coach_blurb"] == "Nice work."
    assert seen == [0], f"{seen[0]} connection(s) held during the Gemini call"


def test_prompt_handles_phrase_without_timing():
    p = coach.build_prompt({**SCORE, "phrases": [{"rating": "okay", "pitch": 60, "timing": None, "coverage": 1.0}]}, 1)
    assert "no timing score" in p
