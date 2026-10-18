"""Public/private rooms, the room list and password joins (database tests: see api/tests/conftest.py)."""
import os

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
    return c.post("/api/rooms", json={"duet": True, **body}, headers=h)


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
