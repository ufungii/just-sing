"""Public/private rooms, the room list and password joins (database tests: see api/tests/conftest.py)."""
import os
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from api import rooms
from api.db import get_engine
from api.main import app
from api.seed import seed

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")


@pytest.fixture
def world():
    seed()
    rooms._wrong_password_log.clear()
    rooms._join_log.clear()
    ids = []
    with TestClient(app) as c:
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
            rooms_of = "(select id from room where host_guest_id=:g)"
            m = f"(select id from match where guest_id=:g or room_id in {rooms_of})"
            for sql in (f"delete from turn_attempt where match_id in {m}",
                        f"delete from match_player where match_id in {m}",
                        f"delete from match where guest_id=:g or room_id in {rooms_of}",
                        f"delete from room_member where room_id in {rooms_of} or guest_id=:g",
                        "delete from room where host_guest_id=:g",
                        "delete from guest_session where id=:g"):
                conn.execute(text(sql), {"g": g})


def make(c, h, **body):
    """Create a room and mark its host as connected (tests have no real socket), like a host with the lobby open."""
    r = c.post("/api/rooms", json={"duet": True, **body}, headers=h)
    if r.status_code == 200:
        connect(r.json()["id"])
    return r


def connect(room_id, slot=0):
    # Lightweight presence for list tests; socket behavior is exercised separately.
    rid = uuid.UUID(str(room_id))
    class FakeSocket:
        async def send_json(self, event):
            pass
    ws = FakeSocket()
    rooms.hub.connect(rid, ws, slot)
    return ws


def disconnect(room_id):
    rid = uuid.UUID(str(room_id))
    for ws, _ in rooms.hub.connections(rid):
        rooms.hub.disconnect(rid, ws)


def test_create_without_a_song_uses_a_default_and_hides_secrets(world):
    c, guest = world
    r = make(c, guest("HostA"), visibility="private", password="abc")
    assert r.status_code == 200
    body = r.json()
    assert body["visibility"] == "private" and body["clip_id"]
    assert "password" not in str(body).lower() and "scrypt" not in str(body)


@pytest.mark.parametrize("password", [None, "", "ab", "x" * 17])
def test_private_room_needs_a_3_to_16_character_password(world, password):
    c, guest = world
    r = make(c, guest("HostB"), visibility="private", password=password)
    assert r.status_code in (400, 422)


def test_password_hash_is_salted_and_checks(world):
    a, b = rooms.hash_password("abc"), rooms.hash_password("abc")
    assert a != b and rooms.check_password("abc", a) and not rooms.check_password("abd", a)
    assert not rooms.check_password("abc", "garbage")


def test_list_filters_searches_and_hides_full_or_started_rooms(world):
    c, guest = world
    pub, priv, other = guest("ListHostPub"), guest("ListHostPriv"), guest("Someone")
    rp = make(c, pub, visibility="public").json()
    make(c, priv, visibility="private", password="pw1")

    everything = c.get("/api/rooms", headers=other).json()
    mine = {r["host_name"]: r for r in everything if r["host_name"].startswith("ListHost")}
    assert set(mine) == {"ListHostPub", "ListHostPriv"}
    assert mine["ListHostPriv"]["visibility"] == "private" and mine["ListHostPub"]["players"] == 1
    assert not any("code" in r or "password" in str(r) for r in everything)

    only_private = c.get("/api/rooms?visibility=private", headers=other).json()
    assert {r["host_name"] for r in only_private if r["host_name"].startswith("ListHost")} == {"ListHostPriv"}
    assert [r["host_name"] for r in c.get("/api/rooms?q=listhostpub", headers=other).json()] == ["ListHostPub"]
    assert c.get("/api/rooms?q=%25", headers=other).json() == []  # a literal % matches nothing

    assert c.post(f"/api/rooms/{rp['id']}/join", json={}, headers=other).status_code == 200
    third = guest("ThirdPlayer")
    assert all(r["host_name"] != "ListHostPub" for r in c.get("/api/rooms", headers=third).json())  # full: gone for everyone else


def test_private_join_needs_the_password_by_id_and_by_code(world):
    c, guest = world
    host, joiner = guest("PwHost"), guest("PwJoiner")
    room = make(c, host, visibility="private", password="secret").json()
    assert c.post(f"/api/rooms/{room['id']}/join", json={}, headers=joiner).status_code == 403
    assert c.post(f"/api/rooms/{room['id']}/join", json={"password": "nope"}, headers=joiner).json()["error"]["code"] == "wrong_password"
    # the join-by-code endpoint must not be a way around the password
    assert c.post("/api/rooms/join", json={"code": room["code"]}, headers=joiner).status_code == 403
    ok = c.post(f"/api/rooms/{room['id']}/join", json={"password": "secret"}, headers=joiner)
    assert ok.status_code == 200 and ok.json()["you"] == 1


def test_public_room_joins_by_code_without_a_password(world):
    c, guest = world
    host, joiner = guest("PubHost"), guest("PubJoiner")
    room = make(c, host).json()
    assert room["visibility"] == "public"
    assert c.post("/api/rooms/join", json={"code": room["code"]}, headers=joiner).json()["you"] == 1


def test_wrong_passwords_are_rate_limited(world):
    c, guest = world
    host, joiner = guest("RlHost"), guest("RlJoiner")
    room = make(c, host, visibility="private", password="secret").json()
    codes = [c.post(f"/api/rooms/{room['id']}/join", json={"password": f"bad{i}"}, headers=joiner).status_code for i in range(7)]
    assert codes[:5] == [403] * 5 and 429 in codes[5:]
    # even the right password waits out the limit
    assert c.post(f"/api/rooms/{room['id']}/join", json={"password": "secret"}, headers=joiner).status_code == 429


def test_your_own_rooms_stay_listed_even_when_full(world):
    c, guest = world
    host, joiner = guest("MineHost"), guest("MineJoiner")
    room = make(c, host).json()
    c.post(f"/api/rooms/{room['id']}/join", json={}, headers=joiner)
    mine = [r for r in c.get("/api/rooms", headers=joiner).json() if r["id"] == room["id"]]
    assert len(mine) == 1 and mine[0]["mine"] is True and mine[0]["players"] == 2
    # a stranger no longer sees it
    other = guest("MineStranger")
    assert all(r["id"] != room["id"] for r in c.get("/api/rooms", headers=other).json())
    # joining again just returns your seat (and needs no password)
    assert c.post(f"/api/rooms/{room['id']}/join", json={}, headers=joiner).json()["you"] == 1


# ---- abandoned lobbies close ----------------------------------------------------------------------

def _state(room_id):
    with get_engine().connect() as conn:
        return conn.execute(text("select state, state_version from room where id=:i"), {"i": room_id}).one()


def test_room_without_a_connection_is_hidden_from_the_list_but_not_from_its_member(world):
    c, guest = world
    host, other = guest("GoneHost"), guest("GoneViewer")
    room = make(c, host).json()
    assert any(r["id"] == room["id"] for r in c.get("/api/rooms", headers=other).json())
    disconnect(room["id"])
    assert all(r["id"] != room["id"] for r in c.get("/api/rooms", headers=other).json())
    assert any(r["id"] == room["id"] and r["mine"] for r in c.get("/api/rooms", headers=host).json())  # can still find the way back
    connect(room["id"])  # the host reconnects before the sweeper runs
    assert any(r["id"] == room["id"] for r in c.get("/api/rooms", headers=other).json())


def test_abandoned_lobby_closes_only_after_the_grace_period(world, monkeypatch):
    c, guest = world
    host, other = guest("SweepHost"), guest("SweepViewer")
    room = make(c, host).json()
    disconnect(room["id"])
    rooms.hub.empty_since.clear()  # as after a restart: the sweeper has never seen this room
    before = _state(room["id"])
    assert rooms.close_stale_rooms(grace=45, now=1000.0) == 0  # first sighting starts the clock
    assert rooms.close_stale_rooms(grace=45, now=1044.0) == 0  # still inside the grace period
    assert _state(room["id"]).state == "lobby"
    published = []
    monkeypatch.setattr(rooms.hub, "broadcast_threadsafe", lambda rid, event: published.append((rid, event)))
    assert rooms.close_stale_rooms(grace=45, now=1045.0) == 1
    after = _state(room["id"])
    assert after.state == "aborted" and after.state_version == before.state_version + 1
    assert len(published) == 1
    rid, event = published[0]
    assert str(rid) == room["id"] and event["type"] == "room_snapshot"
    assert event["state"] == "aborted" and event["state_version"] == after.state_version
    assert rooms.close_stale_rooms(grace=45, now=2000.0) == 0  # no repeated publication/version bump
    with get_engine().connect() as conn:
        assert conn.execute(text("select state from match where room_id=:i"), {"i": room["id"]}).scalar() == "aborted"
    assert all(r["id"] != room["id"] for r in c.get("/api/rooms", headers=other).json())
    assert c.get(f"/api/rooms/{room['id']}", headers=host).json()["state"] == "aborted"


def test_reconnecting_inside_the_grace_period_keeps_the_room(world):
    c, guest = world
    host = guest("BackHost")
    room = make(c, host).json()
    disconnect(room["id"])
    rooms.hub.empty_since.clear()
    rooms.close_stale_rooms(grace=45, now=2000.0)
    connect(room["id"])  # a socket opens again: the clock is dropped
    assert rooms.close_stale_rooms(grace=45, now=2100.0) == 0
    assert _state(room["id"]).state == "lobby"
    disconnect(room["id"])
    rooms.hub.empty_since.clear()
    assert rooms.close_stale_rooms(grace=45, now=2200.0) == 0  # a fresh clock, not the old one
    assert _state(room["id"]).state == "lobby"


def test_a_room_that_is_playing_is_never_swept(world):
    c, guest = world
    host = guest("PlayingHost")
    room = make(c, host).json()
    with get_engine().begin() as conn:
        conn.execute(text("update room set state='playing' where id=:i"), {"i": room["id"]})
    disconnect(room["id"])
    rooms.hub.empty_since.clear()
    rooms.close_stale_rooms(grace=45, now=3000.0)
    assert rooms.close_stale_rooms(grace=45, now=9000.0) == 0
    assert _state(room["id"]).state == "playing"


def test_new_room_clock_starts_at_creation_not_first_sweep(world):
    c, guest = world
    host = guest("NewEmptyHost")
    room = c.post("/api/rooms", json={"duet": True}, headers=host).json()
    rid = uuid.UUID(room["id"])
    created = rooms.hub.empty_since[rid]
    assert rooms.close_stale_rooms(now=created + 44.99) == 0
    assert rooms.close_stale_rooms(now=created + 45) == 1
    assert _state(room["id"]).state == "aborted"


def test_last_socket_disconnect_starts_a_fresh_grace_period(world):
    c, guest = world
    host = guest("TabsHost")
    room = make(c, host).json()
    rid = uuid.UUID(room["id"])
    tab = connect(rid)
    first = rooms.hub.connections(rid)[0][0]
    rooms.hub.disconnect(rid, first)
    assert rid not in rooms.hub.empty_since  # another tab still owns a connection
    rooms.hub.disconnect(rid, tab)
    gone = rooms.hub.empty_since[rid]
    assert rid not in rooms.hub.sockets
    assert rooms.close_stale_rooms(now=gone + 44.99) == 0
    assert rooms.close_stale_rooms(now=gone + 45) == 1


def test_presence_reads_and_unknown_disconnect_do_not_create_phantom_rooms():
    hub = rooms.Hub()
    rid = uuid.uuid4()
    assert not hub.present(rid)
    assert hub.connections(rid) == []
    hub.disconnect(rid, object())
    assert rid not in hub.sockets and rid not in hub.empty_since


def test_reconnect_during_sweep_is_rechecked_under_room_lock(world, monkeypatch):
    c, guest = world
    host = guest("RaceReconnect")
    room = make(c, host).json()
    rid = uuid.UUID(room["id"])
    disconnect(rid)
    gone = rooms.hub.empty_since[rid]
    original = rooms.hub.mark_empty
    calls = 0
    ws = object()

    def reconnect_after_first_check(room_id, now):
        nonlocal calls
        result = original(room_id, now)
        calls += 1
        if calls == 1:
            assert rooms._ws_slot(host["cookie"].split("=", 1)[1], None, rid, ws) == 0
        return result

    monkeypatch.setattr(rooms.hub, "mark_empty", reconnect_after_first_check)
    assert rooms.close_stale_rooms(now=gone + 45) == 0
    assert _state(rid).state == "lobby" and rooms.hub.present(rid) == {0}
    rooms.hub.disconnect(rid, ws)


def test_sweep_winning_room_lock_refuses_late_socket_admission(world, monkeypatch):
    c, guest = world
    host = guest("RaceClose")
    room = make(c, host).json()
    rid = uuid.UUID(room["id"])
    disconnect(rid)
    gone = rooms.hub.empty_since[rid]
    sweep_locked, release_sweep, admission_started = Event(), Event(), Event()
    original_latest = rooms._latest_match
    original_get = rooms.Session.get
    ws = object()

    def pause_locked_sweep(session, current):
        sweep_locked.set()
        assert release_sweep.wait(5)
        return original_latest(session, current)

    def notice_admission(session, entity, ident, **kwargs):
        if entity is rooms.Room and ident == rid and kwargs.get("with_for_update") and sweep_locked.is_set():
            admission_started.set()
        return original_get(session, entity, ident, **kwargs)

    monkeypatch.setattr(rooms, "_latest_match", pause_locked_sweep)
    monkeypatch.setattr(rooms.Session, "get", notice_admission)
    with ThreadPoolExecutor(max_workers=2) as pool:
        sweep = pool.submit(rooms.close_stale_rooms, now=gone + 45)
        try:
            assert sweep_locked.wait(5)
            admission = pool.submit(rooms._ws_slot, host["cookie"].split("=", 1)[1], None, rid, ws)
            assert admission_started.wait(5)
            assert not admission.done()  # blocked on the Room row until close commits
        finally:
            release_sweep.set()
        assert sweep.result(timeout=5) == 1
        assert admission.result(timeout=5) is None
    assert _state(rid).state == "aborted"
    assert rid not in rooms.hub.sockets and not rooms.hub.present(rid)


def test_real_websocket_reconnect_clears_grace_and_cleanup_restarts_it(world):
    c, guest = world
    host = guest("SocketGrace")
    room = c.post("/api/rooms", json={"duet": True}, headers=host).json()
    rid = uuid.UUID(room["id"])
    created = rooms.hub.empty_since[rid]
    with c.websocket_connect(f"/ws/rooms/{rid}", headers=host) as ws:
        event = ws.receive_json()
        assert event["members"][0]["connected"]
        assert rid not in rooms.hub.empty_since
        assert rooms.close_stale_rooms(now=created + 60) == 0
    disconnected = rooms.hub.empty_since[rid]
    assert rid not in rooms.hub.sockets
    with c.websocket_connect(f"/ws/rooms/{rid}", headers=host) as ws:
        assert ws.receive_json()["members"][0]["connected"]
        assert rid not in rooms.hub.empty_since
        assert rooms.close_stale_rooms(now=disconnected + 60) == 0
    assert rooms.hub.empty_since[rid] >= disconnected
    assert _state(rid).state == "lobby"


def test_cancelled_socket_admission_does_not_leave_phantom_presence(monkeypatch):
    rid = uuid.uuid4()
    started, release = Event(), Event()

    class Socket:
        headers = {}
        cookies = {}

    ws = Socket()

    def delayed_admission(token, bearer, room_id, socket):
        started.set()
        assert release.wait(5)
        rooms.hub.connect(room_id, socket, 0)
        return 0

    monkeypatch.setattr(rooms, "_ws_slot", delayed_admission)

    async def scenario():
        discarded = asyncio.Event()
        original = rooms.hub.disconnect

        def disconnect(room_id, socket):
            original(room_id, socket)
            discarded.set()

        monkeypatch.setattr(rooms.hub, "disconnect", disconnect)
        task = asyncio.create_task(rooms.room_socket(ws, rid))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            release.set()
        await asyncio.wait_for(discarded.wait(), 5)
        assert rid not in rooms.hub.sockets

    asyncio.run(scenario())


def test_disconnected_lobbies_do_not_fill_the_list_limit_ahead_of_connected_rooms(world):
    c, guest = world
    host, viewer = guest("OlderLiveHost"), guest("LimitViewer")
    live = make(c, host).json()
    # These newer empty rooms would fill the SQL limit if presence were filtered
    # only after fetching the newest rows. They are intentionally still in grace.
    ghosts = [c.post("/api/rooms", json={"duet": True}, headers=host).json()["id"]
              for _ in range(rooms.LIST_LIMIT)]
    listed = c.get("/api/rooms", headers=viewer).json()
    assert [r["id"] for r in listed] == [live["id"]]
    # The caller's own rooms remain available for reconnect despite this filter.
    owned = c.get("/api/rooms", headers=host).json()
    assert {r["id"] for r in owned} == {live["id"], *ghosts}
    assert all(r["mine"] for r in owned)
