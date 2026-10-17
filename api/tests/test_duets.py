"""Continuous local/online matches: exact ownership, one start barrier, concurrent saves."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from api import play
from api.tests.test_rooms import world, hang_guard
from api.tests.test_play import ph

pytestmark = pytest.mark.skipif(not os.getenv('DATABASE_URL'), reason='needs DATABASE_URL')


def online(c, host, guest):
    room = c.post('/api/rooms', json={'clip_id': 'duet-demo', 'duet': True}, headers=host).json()
    assert c.post('/api/rooms/join', json={'code': room['code']}, headers=guest).status_code == 200
    return room


def start(c, room, host, guest):
    for h in (host, guest):
        assert c.post(f"/api/rooms/{room['id']}/ready", json={'ready': True}, headers=h).status_code == 200
    result = c.post(f"/api/rooms/{room['id']}/start", headers=host)
    assert result.status_code == 200
    return result.json()['match_id']


def loaded(c, mid, headers, slot, register=0):
    return c.post(f'/api/matches/{mid}/duet/ready', json={'players': [{'slot': slot, 'register': register}]}, headers=headers)


def advance(monkeypatch):
    class Later(datetime):
        @classmethod
        def now(cls, tz=None): return datetime.now(tz) + timedelta(seconds=10)
    monkeypatch.setattr(play, 'datetime', Later)


def test_local_single_schedule_both_registers_concurrent_results_and_history(world, monkeypatch):
    c, guest = world
    host = guest('local-duet')
    created = c.post('/api/matches', json={'clip_id': 'duet-demo', 'players': ['A', 'B'], 'duet': True}, headers=host)
    assert created.status_code == 200
    mid = created.json()['match_id']
    url = f'/api/matches/{mid}'
    view = c.get(url, headers=host).json()
    assert view['state'] == 'preparing' and len(view['attempts']) == 2
    a, b = [v['id'] for v in view['attempts']]
    assert c.post(f'/api/turns/{a}/begin', json={}, headers=host).json()['error']['code'] == 'use_duet_ready'
    payload = {'players': [{'slot': 0, 'register': -12}, {'slot': 1, 'register': 12}]}
    ready = c.post(f'{url}/duet/ready', json=payload, headers=host).json()
    assert ready['state'] == 'active'
    assert ready['duet']['start_at'] > ready['server_time'] + 4
    assert [a['register'] for a in ready['attempts']] == [-12, 12]
    assert c.post(f'{url}/duet/ready', json=payload, headers=host).json()['duet']['start_at'] == ready['duet']['start_at']
    data = [ph('d1', 'd2', 'd3', 'd7', 'd8', 'd9'), ph('d4', 'd5', 'd6', pitch=60)]
    assert c.post(f'/api/turns/{a}/result', json=data[0], headers={**host, 'Idempotency-Key': 'early'}).status_code == 409
    advance(monkeypatch)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda pair: c.post(f'/api/turns/{pair[0]}/result', json=pair[1],
            headers={**host, 'Idempotency-Key': pair[0]}), zip((a, b), data)))
    assert [r.status_code for r in responses] == [200, 200]
    assert all(r.json()['range'] is None and r.json()['duet'] for r in responses)
    final = c.get(url, headers=host).json()
    assert final['state'] == 'finished' and final['winner_slot'] == 0
    assert len(final['attempts']) == 2  # no second replay/turn was created
    history = c.get('/api/history', headers=host).json()[0]
    assert history['duet'] and history['range'] is None
    replay = c.post(f'/api/turns/{a}/result', json=data[0], headers={**host, 'Idempotency-Key': a})
    assert replay.status_code == 200
    again = c.post(f'{url}/rematch', headers=host).json()
    assert c.get(f"/api/matches/{again['match_id']}", headers=host).json()['duet']['start_at'] is None


def test_online_barrier_ownership_and_only_finishes_after_both_results(world, monkeypatch):
    c, guest = world
    host, rival = guest('host'), guest('rival')
    room = online(c, host, rival)
    mid = start(c, room, host, rival)
    assert loaded(c, mid, rival, 0).status_code == 403
    first = loaded(c, mid, host, 0).json()
    assert first['state'] == 'preparing' and first['duet']['start_at'] is None
    both = loaded(c, mid, rival, 1).json()
    assert both['state'] == 'active' and all(a['state'] == 'started' for a in both['attempts'])
    assert loaded(c, mid, host, 0).json()['duet']['start_at'] == both['duet']['start_at']
    assert loaded(c, mid, host, 0, register=12).status_code == 409
    a, b = [a['id'] for a in both['attempts']]
    advance(monkeypatch)
    assert c.post(f'/api/turns/{b}/result', json=ph('d4', 'd5', 'd6'), headers={**host, 'Idempotency-Key': 'steal'}).status_code == 403
    wrong = c.post(f'/api/turns/{a}/result', json=ph('d1', 'd4'), headers={**host, 'Idempotency-Key': 'wrong'})
    assert wrong.status_code == 422 and wrong.json()['error']['code'] == 'phrase_mismatch'
    assert c.post(f'/api/turns/{b}/result', json=ph('d4', 'd5', 'd6'), headers={**rival, 'Idempotency-Key': 'b'}).status_code == 200
    assert c.get(f'/api/matches/{mid}', headers=host).json()['state'] == 'active'
    assert c.post(f'/api/turns/{a}/result', json=ph('d1', 'd2', 'd3', 'd7', 'd8', 'd9'), headers={**host, 'Idempotency-Key': 'a'}).status_code == 200
    assert c.get(f"/api/rooms/{room['id']}", headers=rival).json()['state'] == 'finished'
    assert c.post(f'/api/turns/{b}/result', json=ph('d4', 'd5', 'd6'), headers={**host, 'Idempotency-Key': 'b'}).status_code == 403
    assert all(c.get('/api/history', headers=h).json()[0]['range'] is None for h in (host, rival))


def test_range_keeps_authored_slots_rejects_empty_singer_and_restarts_only_together(world):
    c, guest = world
    host, rival = guest('host'), guest('rival')
    room = online(c, host, rival)
    url = f"/api/rooms/{room['id']}"
    bad = c.post(f'{url}/range', json={'range': {'start': 0, 'end': 8.5}}, headers=host)
    assert bad.status_code == 422 and bad.json()['error']['code'] == 'invalid_duet_range'
    rng = {'start': 9.0, 'end': 26.5}
    assert c.post(f'{url}/range', json={'range': rng}, headers=host).status_code == 200
    mid = start(c, room, host, rival)
    view = loaded(c, mid, host, 0).json()
    assert [s['slot'] for s in view['duet']['sections']] == [1, 0]
    loaded(c, mid, rival, 1)
    assert c.post(f'/api/matches/{mid}/retry', headers=host).json()['error']['code'] == 'restart_duet'
    stopped = c.post(f'/api/matches/{mid}/duet/stop', headers=rival).json()
    assert stopped['state'] == 'retry_required'
    assert c.post(f'{url}/rematch', headers=rival).status_code == 403
    new = c.post(f'{url}/rematch', headers=host).json()
    snapshot = c.get(url, headers=rival).json()
    assert snapshot['range'] == rng
    assert snapshot['match']['duet']['start_at'] is None and snapshot['match']['state'] == 'preparing'
    assert new['match_id'] != mid


def test_reload_after_scheduled_start_is_refused_without_moving_the_schedule(world, monkeypatch):
    from api import duet_play
    c, guest = world
    host, rival = guest('host'), guest('rival')
    room = online(c, host, rival)
    mid = start(c, room, host, rival)
    loaded(c, mid, host, 0)
    frozen = loaded(c, mid, rival, 1).json()['duet']['start_at']
    class Later(datetime):
        @classmethod
        def now(cls, tz=None): return datetime.now(tz) + timedelta(seconds=10)
    monkeypatch.setattr(duet_play, 'datetime', Later)
    response = loaded(c, mid, rival, 1)
    assert response.status_code == 409 and response.json()['error']['code'] == 'missed_start'
    view = c.get(f'/api/matches/{mid}', headers=host).json()
    assert view['duet']['start_at'] == frozen and len(view['attempts']) == 2


def test_concurrent_loaded_barrier_follows_authored_non_alternating_ownership(world, monkeypatch):
    c, guest = world
    song = play.CATALOG['duet-demo']
    authored = song.model_copy(update={'duet_sections': [
        section.model_copy(update={'slot': 1 if index < 2 else 0})
        for index, section in enumerate(song.duet_sections)]})
    monkeypatch.setitem(play.CATALOG, song.id, authored)
    host, rival = guest('host'), guest('rival')
    room = online(c, host, rival)
    mid = start(c, room, host, rival)
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(lambda pair: loaded(c, mid, pair[0], pair[1]), [(host, 0), (rival, 1)]))
    assert all(r.status_code == 200 for r in responses)
    current = c.get(f'/api/matches/{mid}', headers=host).json()
    assert current['state'] == 'active' and all(a['state'] == 'started' for a in current['attempts'])
    assert [s['slot'] for s in current['duet']['sections']] == [1, 1, 0]
    for response in responses:
        returned = response.json()['duet']['start_at']
        assert returned is None or returned == current['duet']['start_at']
    advance(monkeypatch)
    for slot, (headers, ids) in enumerate([(host, ['d7', 'd8', 'd9']), (rival, ['d1', 'd2', 'd3', 'd4', 'd5', 'd6'])]):
        aid = next(a['id'] for a in current['attempts'] if a['slot'] == slot)
        response = c.post(f'/api/turns/{aid}/result', json=ph(*ids), headers={**headers, 'Idempotency-Key': str(slot)})
        assert response.status_code == 200 and response.json()['range'] is None
        assert [p['phrase_id'] for p in response.json()['phrases']] == ids
    assert c.get(f'/api/matches/{mid}', headers=host).json()['state'] == 'finished'
