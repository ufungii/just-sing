"""Online rooms against the real dev database (skipped without DATABASE_URL): lobby rules, seat-based
turns, WebSocket events, racing joins, and recovery of a lost turn. One TestClient is used for every
player (identity is the cookie header) so all sockets share one event loop."""
import os
import signal
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from api.db import get_engine
from api.main import app
from api.retention import reconcile_attempts
from api.seed import seed

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")

RESULT = lambda pitch: {"phrases": [{"phrase_id": "p1", "rating": "great", "pitch": pitch, "timing": pitch, "coverage": 1}]}


@pytest.fixture(autouse=True)
def hang_guard():
    """A broken websocket test would block forever; fail it after 90 s instead."""
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError("test hung")))
    signal.alarm(90)
    yield
    signal.alarm(0)


@pytest.fixture
def world():
    seed()
    ids = []
    with TestClient(app) as c:  # entering the context starts the app's event loop for broadcasts
        def guest(name):
            c.cookies.clear()
            gid = c.post("/api/guests", json={"display_name": name}).json()["id"]
            ids.append(gid)
            h = {"cookie": f"guest_token={c.cookies.get('guest_token')}"}
            c.cookies.clear()
            return h
        yield c, guest
    with get_engine().begin() as conn:
        for g in ids:
            rooms = "(select id from room where host_guest_id=:g)"
            m = f"(select id from match where guest_id=:g or room_id in {rooms})"
            for sql in (f"delete from turn_attempt where match_id in {m}",
                        f"delete from match_player where match_id in {m}",
                        f"delete from match where guest_id=:g or room_id in {rooms}",
                        f"delete from room_member where room_id in {rooms} or guest_id=:g",
                        "delete from room where host_guest_id=:g",
                        "delete from guest_session where id=:g"):
                conn.execute(text(sql), {"g": g})


def until(ws, type_, predicate=lambda e: True):
    for _ in range(20):
        e = ws.receive_json()
        if e["type"] == type_ and predicate(e):
            return e
    raise AssertionError(f"never saw {type_}")


def open_room(c, host, guest):
    room = c.post("/api/rooms", json={"clip_id": "synthetic-demo"}, headers=host).json()
    assert c.post("/api/rooms/join", json={"code": room["code"].lower()}, headers=guest).status_code == 200
    return room


def test_room_flow_with_websocket_events(world):
    c, guest = world
    host, bo, third = guest("host"), guest("bo"), guest("third")
    room = open_room(c, host, bo)
    rid = room["id"]

    assert c.post("/api/rooms/join", json={"code": room["code"]}, headers=third).json()["error"]["code"] == "room_full"
    assert c.get(f"/api/rooms/{rid}", headers=third).status_code == 404  # non-members cannot see it
    assert c.post(f"/api/rooms/{rid}/start", headers=host).json()["error"]["code"] == "not_ready"
    for h in (host, bo):
        assert c.post(f"/api/rooms/{rid}/ready", json={"ready": True}, headers=h).status_code == 200
    assert c.post(f"/api/rooms/{rid}/start", headers=bo).status_code == 403  # host only

    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect(f"/ws/rooms/{rid}", headers={**host, "origin": "https://evil.example"}):
            pass
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect(f"/ws/rooms/{rid}", headers=third):
            pass

    with c.websocket_connect(f"/ws/rooms/{rid}", headers=host) as hws, \
            c.websocket_connect(f"/ws/rooms/{rid}", headers=bo) as bws:
        both = lambda e: all(m["connected"] for m in e["members"])
        until(hws, "room_snapshot", both)  # presence reaches the host
        until(bws, "room_snapshot", both)

        start = c.post(f"/api/rooms/{rid}/start", headers=host).json()
        playing = until(bws, "room_snapshot", lambda e: e["state"] == "playing")
        assert playing["match"]["active_slot"] == 0
        a0 = start["attempt_id"]
        assert c.post(f"/api/turns/{a0}/begin", json={}, headers=third).status_code == 404
        assert c.post(f"/api/turns/{a0}/begin", json={}, headers=bo).json()["error"]["code"] == "not_your_seat"
        assert c.post(f"/api/turns/{a0}/begin", json={}, headers=host).status_code == 200

        hws.send_json({"type": "progress", "data": {"t": 1.5}})
        assert until(bws, "turn_progress")["data"] == {"t": 1.5}
        bws.send_json({"type": "progress", "data": {}})  # not the singer
        assert until(bws, "error")["code"] == "not_your_turn"
        hws.send_text("x" * 5000)
        assert until(hws, "error")["code"] == "rate_limited"

        r = c.post(f"/api/turns/{a0}/result", json=RESULT(70), headers={**host, "Idempotency-Key": "a"})
        assert r.status_code == 200
        until(bws, "result_saved", lambda e: e["slot"] == 0)
        a1 = next(a["id"] for a in until(hws, "room_snapshot", lambda e: e["match"]["active_slot"] == 1)["match"]["attempts"]
                  if a["slot"] == 1)
        assert c.post(f"/api/turns/{a1}/begin", json={}, headers=bo).status_code == 200
        c.post(f"/api/turns/{a1}/result", json=RESULT(90), headers={**bo, "Idempotency-Key": "b"})
        until(hws, "match_finished")

    seen = [c.get(f"/api/rooms/{rid}", headers=h).json() for h in (host, bo)]
    assert seen[0]["state"] == "finished" and seen[0]["match"]["winner_slot"] == 1 == seen[1]["match"]["winner_slot"]
    assert c.get("/api/history", headers=bo).json()[0]["total"] == pytest.approx(90)  # their own seat
    again = c.post(f"/api/rooms/{rid}/rematch", headers=host)
    assert again.status_code == 200 and c.get(f"/api/rooms/{rid}", headers=bo).json()["state"] == "playing"


def test_racing_joins_fill_exactly_one_seat(world):
    c, guest = world
    host = guest("host")
    code = c.post("/api/rooms", json={"clip_id": "synthetic-demo"}, headers=host).json()["code"]
    racers = [guest(f"r{i}") for i in range(4)]
    with ThreadPoolExecutor(4) as pool:
        codes = list(pool.map(lambda h: c.post("/api/rooms/join", json={"code": code}, headers=h).status_code, racers))
    assert sorted(codes) == [200, 409, 409, 409]


def test_lost_turn_is_recovered_without_double_scoring(world):
    c, guest = world
    host, bo = guest("host"), guest("bo")
    room = open_room(c, host, bo)
    for h in (host, bo):
        c.post(f"/api/rooms/{room['id']}/ready", json={"ready": True}, headers=h)
    start = c.post(f"/api/rooms/{room['id']}/start", headers=host).json()
    old = start["attempt_id"]
    c.post(f"/api/turns/{old}/begin", json={}, headers=host)

    with get_engine().begin() as conn:  # the singer's tab died and the deadline passed
        conn.execute(text("update turn_attempt set deadline_at = now() - interval '1 second' where id=:i"), {"i": old})
    assert reconcile_attempts() >= 1
    assert c.get(f"/api/matches/{start['match_id']}", headers=host).json()["state"] == "retry_required"
    late = c.post(f"/api/turns/{old}/result", json=RESULT(99), headers={**host, "Idempotency-Key": "late"})
    assert late.json()["error"]["code"] == "attempt_invalidated"  # cannot overwrite anything

    assert c.post(f"/api/matches/{start['match_id']}/retry", headers=bo).status_code == 403  # not their seat
    new = c.post(f"/api/matches/{start['match_id']}/retry", headers=host).json()["attempt_id"]
    assert new != old
    c.post(f"/api/turns/{new}/begin", json={}, headers=host)
    assert c.post(f"/api/turns/{new}/result", json=RESULT(80), headers={**host, "Idempotency-Key": "ok"}).status_code == 200
    view = c.get(f"/api/matches/{start['match_id']}", headers=host).json()
    assert [a["state"] for a in view["attempts"] if a["slot"] == 0].count("accepted") == 1
    assert view["active_slot"] == 1


def test_binary_frame_gets_an_error_and_the_socket_survives(world):
    """Regression: receive_text raised KeyError on a binary frame, killing the connection."""
    c, guest = world
    host, bo = guest("host"), guest("bo")
    room = open_room(c, host, bo)
    with c.websocket_connect(f"/ws/rooms/{room['id']}", headers=host) as ws:
        until(ws, "room_snapshot")
        ws.send_bytes(b"\x00\x01\x02")
        assert until(ws, "error")["code"] == "bad_message"
        ws.send_json({"type": "heartbeat"})
        until(ws, "heartbeat_ack")  # still alive
