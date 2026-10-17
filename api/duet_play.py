"""Two loaded clients, one durable future start; never replay an individual singer's song."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import play
from .duets import metadata
from .errors import ApiError
from .models import TimeRange
from .tables import Match, RoomMember, TurnAttempt

router = APIRouter(prefix='/api')
# Count-in plus network scheduling margin, after BOTH clients have loaded audio/opened mic.
START_LEAD = 5.0


class PlayerReady(BaseModel):
    slot: int = Field(ge=0, le=1)
    register: int = 0
    calibration_offset: float | None = None


class DuetReady(BaseModel):
    players: list[PlayerReady] = Field(min_length=1, max_length=2)


@router.get('/time')
def server_time():
    return {'server_time': datetime.now(timezone.utc).timestamp()}


@router.post('/matches/{match_id}/duet/ready')
def ready(match_id: uuid.UUID, body: DuetReady, guest=Depends(play.current_guest), s: Session = Depends(play.get_db)):
    match = s.get(Match, match_id, with_for_update=True, populate_existing=True)
    play._owned_match(s, guest, match_id)
    config = play._match_duet(s, match)
    if not config or match.state not in ('preparing', 'active'):
        raise ApiError(409, 'duet_closed', 'This duet cannot be prepared; restart together.')
    song = play._frozen_song(match)
    if config.get('start_at') and datetime.now(timezone.utc).timestamp() >= config['start_at']:
        raise ApiError(409, 'missed_start', 'The shared start was missed. Restart the whole duet together.')
    expected_slots = [0, 1]
    if match.room_id:
        expected_slots = [s.scalar(select(RoomMember.slot).where(RoomMember.room_id == match.room_id,
                                                               RoomMember.guest_id == guest.id))]
    if sorted(p.slot for p in body.players) != expected_slots:
        raise ApiError(403, 'not_your_seat', 'Prepare only your own microphone and voice range.')
    attempts = s.scalars(select(TurnAttempt).where(TurnAttempt.match_id == match.id)
                         .order_by(TurnAttempt.slot).with_for_update()).all()
    for player in body.players:
        if player.register not in (-12, 0, 12):
            raise ApiError(422, 'invalid_register', 'register must be -12, 0 or 12.')
        attempt = next(a for a in attempts if a.slot == player.slot)
        already_loaded = bool(isinstance(attempt.phrase_results, dict) and attempt.phrase_results.get('loaded'))
        if already_loaded and (attempt.register != player.register or attempt.calibration_offset != player.calibration_offset):
            raise ApiError(409, 'attempt_already_started', 'Voice settings are frozen after ready.')
        if not already_loaded and match.state == 'active':
            raise ApiError(409, 'missed_start', 'The duet already started. Restart the whole song together.')
        attempt.register, attempt.calibration_offset = player.register, player.calibration_offset
        attempt.phrase_results = {'duet': config, 'loaded': True}
    if match.state == 'preparing' and len(attempts) == 2 and all(a.phrase_results.get('loaded') for a in attempts):
        at = datetime.now(timezone.utc) + timedelta(seconds=START_LEAD)
        config = {**config, 'start_at': at.timestamp()}
        rng = TimeRange(**config['range']) if config.get('range') else None
        length = rng.end - rng.start if rng else song.duration
        for attempt in attempts:
            attempt.phrase_results = {'duet': config, 'loaded': True}
            attempt.state, attempt.started_at = 'started', at
            attempt.deadline_at = at + timedelta(seconds=length) + play.RECONNECT_GRACE
        match.state = 'active'
    s.commit()
    play.notify(s, match, 'duet_ready')
    return play.match_view(s, match)


@router.post('/matches/{match_id}/duet/stop')
def stop(match_id: uuid.UUID, guest=Depends(play.current_guest), s: Session = Depends(play.get_db)):
    match = s.get(Match, match_id, with_for_update=True, populate_existing=True)
    play._owned_match(s, guest, match_id)
    if not play._match_duet(s, match) or match.state not in ('preparing', 'active', 'retry_required'):
        raise ApiError(409, 'duet_closed', 'This duet is already closed.')
    for attempt in s.scalars(select(TurnAttempt).where(TurnAttempt.match_id == match.id).with_for_update()):
        if attempt.state != 'accepted':
            attempt.state = 'invalidated'
    match.state = 'retry_required'
    s.commit()
    play.notify(s, match, 'retry_required')
    return play.match_view(s, match)
