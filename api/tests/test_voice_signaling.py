"""Signaling is ephemeral, authenticated to a room, and limited to the opposite duet seat."""
import os

import pytest

from api.rooms import _valid_voice_signal
from api.tests.test_rooms import world, hang_guard, until
from api.tests.test_duets import online, start


def signal(mid='match', kind='ready', **extra):
    return {'match_id': mid, 'session': 'sender', 'kind': kind, **extra}


@pytest.mark.parametrize('data', [None, [], {}, signal(kind='raw_audio'),
    signal(destination='other-room'), signal(kind='offer', peer='receiver', sdp=42),
    signal(kind='ice', peer='receiver', candidate={'candidate': 'x', 'audio': 'forbidden'}),
    signal(kind='ice', peer='receiver', candidate={'candidate': 'x', 'sdpMLineIndex': -1}),
    signal(kind='ice', peer='receiver', candidate={'candidate': 'x', 'sdpMid': []}),
    signal(kind='answer', peer='receiver', sdp='x' * 14001)])
def test_invalid_signal(data):
    assert not _valid_voice_signal(data)


@pytest.mark.parametrize('data', [signal(), signal(kind='offer', peer='receiver', sdp='v=0'),
    signal(kind='answer', peer='receiver', sdp='v=0'),
    signal(kind='ice', peer='receiver', candidate={'candidate': 'x', 'sdpMid': '0', 'sdpMLineIndex': 0})])
def test_valid_signal(data):
    assert _valid_voice_signal(data)


@pytest.mark.skipif(not os.getenv('DATABASE_URL'), reason='needs disposable DATABASE_URL')
def test_voice_only_reaches_opposite_seat_in_current_live_duet(world):
    c, guest = world
    host, rival, outsider = guest('voice-host'), guest('voice-rival'), guest('voice-outsider')
    room = online(c, host, rival)
    rid = room['id']
    with c.websocket_connect(f'/ws/rooms/{rid}', headers=host) as hws, \
            c.websocket_connect(f'/ws/rooms/{rid}', headers=rival) as rws, \
            c.websocket_connect(f'/ws/rooms/{rid}', headers=host) as other_tab:
        until(hws, 'room_snapshot', lambda e: all(m['connected'] for m in e['members']))
        # Lobby mic checks cannot be shared.
        hws.send_json({'type': 'voice_signal', 'data': signal()})
        assert until(hws, 'error')['code'] == 'voice_unavailable'
        mid = start(c, room, host, rival)
        until(rws, 'room_snapshot', lambda e: e['state'] == 'playing')
        hws.send_json({'type': 'voice_signal', 'slot': 1, 'data': signal(mid)})
        ev = until(rws, 'voice_signal')
        assert ev['slot'] == 0 and ev['data'] == signal(mid)  # sender identity is server-owned
        # Same-seat tabs must never receive their own signaling.
        other_tab.send_json({'type': 'heartbeat'})
        while (ev := other_tab.receive_json())['type'] != 'heartbeat_ack':
            assert ev['type'] != 'voice_signal'
        # Valid SDP above the progress budget is relayed, but unrelated messages keep the old limit.
        offer = signal(mid, 'offer', peer='receiver', sdp='v=0\r\n' + 'a=x\r\n' * 700)
        hws.send_json({'type': 'voice_signal', 'data': offer})
        assert until(rws, 'voice_signal')['data'] == offer
        hws.send_json({'type': 'progress', 'data': {'x': 'x' * 3000}})
        assert until(hws, 'error')['code'] == 'rate_limited'
        for data, code in [(signal('old-match'), 'voice_unavailable'), (signal(mid, destination='elsewhere'), 'bad_message')]:
            hws.send_json({'type': 'voice_signal', 'data': data})
            assert until(hws, 'error')['code'] == code
        # Room auth and Origin checks are shared with all existing socket events.
        assert c.get(f'/api/rooms/{rid}', headers=outsider).status_code == 404
        assert c.post(f'/api/matches/{mid}/duet/stop', headers=rival).status_code == 200
        until(hws, 'room_snapshot', lambda e: e['match']['state'] == 'retry_required')
        hws.send_json({'type': 'voice_signal', 'data': signal(mid)})
        assert until(hws, 'error')['code'] == 'voice_unavailable'
