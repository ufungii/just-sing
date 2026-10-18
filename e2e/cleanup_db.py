"""Delete the rows the e2e runs created (guests named "E2E-Bot-<run>" / "E2E-Rival-<run>", their matches, rooms and practice attempts; only guests without a login: a guest with auth0_sub is never deleted) and print
remaining row counts.   PYTHONPATH=. .venv/bin/python e2e/cleanup_db.py        (uses the DB from .env)"""
from dotenv import load_dotenv

load_dotenv()
from sqlalchemy import delete, func, or_, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from api.db import get_engine  # noqa: E402
from api.tables import GuestSession, Match, MatchPlayer, PracticeAttempt, Room, RoomMember, TurnAttempt  # noqa: E402

with Session(get_engine()) as s:
    g = select(GuestSession.id).where(GuestSession.display_name.regexp_match(r"^E2E-(Bot|Rival)-[0-9a-z]{1,4}$"), GuestSession.auth0_sub.is_(None))
    rooms = select(Room.id).where(Room.host_guest_id.in_(g))
    m = select(Match.id).where(or_(Match.guest_id.in_(g), Match.room_id.in_(rooms)))
    s.execute(delete(TurnAttempt).where(TurnAttempt.match_id.in_(m)))
    s.execute(delete(MatchPlayer).where(MatchPlayer.match_id.in_(m)))
    s.execute(delete(Match).where(Match.id.in_(m)))
    s.execute(delete(RoomMember).where(or_(RoomMember.room_id.in_(rooms), RoomMember.guest_id.in_(g))))
    s.execute(delete(Room).where(Room.id.in_(rooms)))
    s.execute(delete(PracticeAttempt).where(PracticeAttempt.guest_id.in_(g)))  # foreign key to the guest
    s.execute(delete(GuestSession).where(GuestSession.id.in_(g)))
    s.commit()
    print({t.__tablename__: s.scalar(select(func.count()).select_from(t)) for t in (GuestSession, Match, TurnAttempt, Room, RoomMember)})
