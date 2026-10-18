import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.db import get_engine
from api.retention import cleanup_expired
from api.seed import seed
from api.tables import GuestSession, Match, MatchPlayer, Room, RoomMember, TurnAttempt

pytestmark = pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs DATABASE_URL")


def test_only_expired_guests_are_removed():
    seed()
    now = datetime.now(timezone.utc)
    ids = {}
    with Session(get_engine()) as s:
        for name, delta, sub in [("old", -1, None), ("live", 1, None), ("acct", -1, "test|keep")]:
            g = GuestSession(display_name=name, token_hash=uuid.uuid4().hex, auth0_sub=sub,
                             expires_at=now + timedelta(days=delta))
            s.add(g); s.flush()
            m = Match(guest_id=g.id, mode="solo", clip_id="synthetic-demo", clip_version=1, scoring_version="t")
            s.add(m); s.flush()
            s.add(MatchPlayer(match_id=m.id, slot=0, display_name=name)); s.flush()
            s.add(TurnAttempt(match_id=m.id, slot=0))
            ids[name] = g.id
        s.commit()
    try:
        assert cleanup_expired() >= 1
        with get_engine().connect() as c:
            alive = {n for n, i in ids.items()
                     if c.execute(text("select 1 from guest_session where id=:i"), {"i": i}).first()}
            assert alive == {"live", "acct"}
            assert c.execute(text("select count(*) from match where guest_id=:i"), {"i": ids["old"]}).scalar() == 0
    finally:
        with get_engine().begin() as c:
            for i in ids.values():
                for t in ("turn_attempt", "match_player"):
                    c.execute(text(f"delete from {t} where match_id in (select id from match where guest_id=:g)"), {"g": i})
                c.execute(text("delete from match where guest_id=:g"), {"g": i})
                c.execute(text("delete from guest_session where id=:g"), {"g": i})


def test_expired_host_of_a_room_with_an_account_keeps_the_online_history():
    """Regression: online matches belong to the host's guest row, so cleaning up an expired host also deleted
    the match history of a logged-in account that played in slot 1."""
    seed()
    now = datetime.now(timezone.utc)
    with Session(get_engine()) as s:
        host = GuestSession(display_name="oldhost", token_hash=uuid.uuid4().hex, expires_at=now - timedelta(days=1))
        acct = GuestSession(display_name="acct", token_hash=uuid.uuid4().hex, auth0_sub=f"test|{uuid.uuid4().hex}",
                            expires_at=now + timedelta(days=1))
        s.add_all([host, acct]); s.flush()
        room = Room(code=uuid.uuid4().hex[:8].upper(), host_guest_id=host.id, clip_id="synthetic-demo", clip_version=1,
                    expires_at=now + timedelta(hours=1))
        s.add(room); s.flush()
        s.add_all([RoomMember(room_id=room.id, slot=0, guest_id=host.id, display_name="oldhost"),
                   RoomMember(room_id=room.id, slot=1, guest_id=acct.id, display_name="acct")])
        match = Match(guest_id=host.id, mode="online", clip_id="synthetic-demo", clip_version=1, scoring_version="t",
                      room_id=room.id)
        s.add(match); s.flush()
        s.add_all([MatchPlayer(match_id=match.id, slot=0, display_name="oldhost"),
                   MatchPlayer(match_id=match.id, slot=1, display_name="acct")])
        s.commit()
        ids = {"host": host.id, "acct": acct.id, "match": match.id, "room": room.id}
    try:
        cleanup_expired()
        with get_engine().connect() as c:
            assert c.execute(text("select 1 from match where id=:i"), {"i": ids["match"]}).first()
            assert c.execute(text("select 1 from guest_session where id=:i"), {"i": ids["host"]}).first()
    finally:
        with get_engine().begin() as c:
            for t in ("turn_attempt", "match_player"):
                c.execute(text(f"delete from {t} where match_id=:m"), {"m": ids["match"]})
            c.execute(text("delete from match where id=:m"), {"m": ids["match"]})
            c.execute(text("delete from room_member where room_id=:r"), {"r": ids["room"]})
            c.execute(text("delete from room where id=:r"), {"r": ids["room"]})
            for g in (ids["host"], ids["acct"]):
                c.execute(text("delete from guest_session where id=:g"), {"g": g})
