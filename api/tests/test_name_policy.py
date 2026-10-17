import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.name_policy import blocked_player_name_reason, validate_player_name

ROOT = Path(__file__).resolve().parents[2]
CASES = json.loads((ROOT / 'contracts/fixtures/player_names.json').read_text())['cases']


@pytest.mark.parametrize('case', CASES, ids=[str(i) for i in range(len(CASES))])
def test_shared_policy(case):
    assert blocked_player_name_reason(case['name']) == case['reason']


def test_all_configured_terms_are_blocked():
    for term in json.loads((ROOT / 'contracts/player-name-policy.json').read_text())['blocked_terms']:
        assert blocked_player_name_reason(term) == 'language', term


def test_validation_rejects_names_but_never_echoes_them():
    assert validate_player_name(' Mina ') == 'Mina'
    for name in ('lorelei', 'sh1t', '   ', 'x' * 41):
        with pytest.raises(ValueError, match='^Choose a different player name.$'):
            validate_player_name(name)


def test_api_inputs_enforce_policy():
    from api.play import GuestIn, MatchIn
    for name in ('ojas', 'n1gg3r'):
        with pytest.raises(ValueError):
            GuestIn(display_name=name)
        with pytest.raises(ValueError):
            MatchIn(clip_id='synthetic-demo', players=['Mina', name])
    assert GuestIn(display_name=' Mina ').display_name == 'Mina'


def test_existing_guest_and_match_paths_reject_before_database_access():
    from api import play, rooms
    from api.errors import ApiError
    guest = SimpleNamespace(display_name='sh1t')
    for call in (
        lambda: play._new_match(None, guest, 'unused', ['sh1t']),
        lambda: rooms.create_room(rooms.RoomIn(clip_id='unused'), guest, None),
        lambda: rooms.join_room(rooms.JoinIn(code='ABC'), guest, None),
    ):
        with pytest.raises(ApiError) as error:
            call()
        assert error.value.code == 'invalid_player_name'
