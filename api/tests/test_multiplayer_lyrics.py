"""Saved, display-only lyrics: real database, exact singer ownership and shared online results."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from api import lyric_check, play
from api.tests.test_duets import advance, loaded, online, start
from api.tests.test_play import ph
from api.tests.test_rooms import world, hang_guard  # noqa: F401

pytestmark = pytest.mark.skipif(not os.getenv('DATABASE_URL'), reason='needs disposable TEST_DATABASE_URL')


@pytest.fixture
def model(monkeypatch, tmp_path):
    fp = tmp_path / 'fingerprints.npz'
    fp.touch()
    monkeypatch.setattr(lyric_check, 'fingerprint_path', lambda _: fp)
    monkeypatch.setattr(lyric_check.practice, '_normalize', lambda *args: tmp_path / 'take.wav')

    class Checker:
        version = 'test'
        calls = []

        def check(self, wav, fingerprints, offset_s, only=None):
            self.calls.append(only)
            # A stray model line must never leak into another singer's feedback.
            return [{'line_index': i, 'status': 'match'} for i in sorted(only)] + [
                {'line_index': 999, 'status': 'unclear'}]

    fake = Checker()
    monkeypatch.setattr(lyric_check, 'checker', fake)
    return fake


def check(c, aid, headers):
    return c.post(f'/api/turns/{aid}/lyric-check', headers=headers,
                  data={'offset_s': '-1.0'}, files={'audio': ('take.wav', b'test')})


def save(c, aid, ids, headers, key, pitch=80):
    body = {**ph(*ids, pitch=pitch), 'check_lyrics': True}
    result = c.post(f'/api/turns/{aid}/result', json=body, headers={**headers, 'Idempotency-Key': key})
    assert result.status_code == 200, result.text
    assert result.json()['lyrics']['status'] == 'pending'
    return result.json()


def test_online_checks_only_own_saved_lines_and_both_clients_see_bars(world, monkeypatch, model):
    c, guest = world
    host, rival, stranger = guest('lyrics-host'), guest('lyrics-rival'), guest('lyrics-stranger')
    room = online(c, host, rival)
    mid = start(c, room, host, rival)
    loaded(c, mid, host, 0)
    view = loaded(c, mid, rival, 1).json()
    a, b = [attempt['id'] for attempt in view['attempts']]
    assert check(c, a, host).status_code == 409
    advance(monkeypatch)
    ids = [['d1', 'd2', 'd3', 'd7', 'd8', 'd9'], ['d4', 'd5', 'd6']]
    before = [save(c, aid, phrases, headers, aid, pitch=80 - slot * 20)
              for slot, (aid, phrases, headers) in enumerate(zip((a, b), ids, (host, rival)))]
    assert check(c, a, rival).status_code == 403
    assert check(c, a, stranger).status_code == 404
    for slot, (aid, headers) in enumerate(zip((a, b), (host, rival))):
        result = check(c, aid, headers)
        assert result.status_code == 200, result.text
        song = play.CATALOG['duet-demo']
        expected = {p.line_index for p in song.phrases if p.id in ids[slot]}
        assert model.calls[-1] == expected
        assert {line['line_index'] for line in result.json()['lines']} == expected
    calls = len(model.calls)
    assert check(c, a, host).status_code == 200
    assert len(model.calls) == calls  # successful uploads are cached
    for headers in (host, rival):
        after = c.get(f'/api/matches/{mid}', headers=headers).json()
        assert after['winner_slot'] == 0
        for slot, attempt in enumerate(after['attempts']):
            score = attempt['score']
            assert score['lyrics']['status'] == 'ok'
            for field in ('total', 'pitch', 'timing', 'phrases'):
                assert score[field] == before[slot][field]
        snapshot = c.get(f"/api/rooms/{room['id']}", headers=headers).json()
        assert all(a['score']['lyrics']['status'] == 'ok' for a in snapshot['match']['attempts'])


def test_local_duet_missing_fingerprints_and_busy_do_not_change_scores(world, monkeypatch, model):
    c, guest = world
    host = guest('local-lyrics')
    created = c.post('/api/matches', json={'clip_id': 'duet-demo', 'players': ['A', 'B'], 'duet': True}, headers=host).json()
    mid = created['match_id']
    view = c.post(f'/api/matches/{mid}/duet/ready', json={'players': [
        {'slot': 0, 'register': 0}, {'slot': 1, 'register': 0}]}, headers=host).json()
    advance(monkeypatch)
    a, b = [attempt['id'] for attempt in view['attempts']]
    score = save(c, a, ['d1', 'd2', 'd3', 'd7', 'd8', 'd9'], host, 'a')
    monkeypatch.setattr(lyric_check, 'LINE_WAIT_S', 0)
    lyric_check.practice._busy.acquire()
    try:
        assert check(c, a, host).status_code == 429
    finally:
        lyric_check.practice._busy.release()
    assert check(c, a, host).json()['status'] == 'ok'
    save(c, b, ['d4', 'd5', 'd6'], host, 'b')
    monkeypatch.setattr(lyric_check, 'fingerprint_path', lambda _: None)
    assert check(c, b, host).json()['status'] == 'unavailable'
    final = c.get(f'/api/matches/{mid}', headers=host).json()
    assert final['attempts'][0]['score']['total'] == score['total']
    assert final['attempts'][1]['score']['lyrics']['status'] == 'unavailable'


def test_abandoned_upload_expires_without_changing_persisted_score():
    from types import SimpleNamespace
    attempt = SimpleNamespace(phrase_results=[{'_lyrics': {'status': 'pending'}}],
                              completed_at=datetime.now(timezone.utc) - timedelta(minutes=4))
    assert play._lyrics(attempt).status == 'unavailable'
    assert attempt.phrase_results[0]['_lyrics']['status'] == 'pending'


def test_slow_lyric_inference_does_not_block_the_other_singers_score(world, monkeypatch, model):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    c, guest = world
    host, rival = guest('slow-lyrics-host'), guest('slow-lyrics-rival')
    room = online(c, host, rival)
    mid = start(c, room, host, rival)
    loaded(c, mid, host, 0)
    view = loaded(c, mid, rival, 1).json()
    a, b = [attempt['id'] for attempt in view['attempts']]
    advance(monkeypatch)
    save(c, a, ['d1', 'd2', 'd3', 'd7', 'd8', 'd9'], host, 'first')
    entered, release = Event(), Event()
    original = model.check

    def slow(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(model, 'check', slow)
    with ThreadPoolExecutor(2) as pool:
        lyrics = pool.submit(check, c, a, host)
        try:
            assert entered.wait(5)
            other = pool.submit(save, c, b, ['d4', 'd5', 'd6'], rival, 'other')
            assert other.result(timeout=5)['total'] == 80
        finally:
            release.set()
        assert lyrics.result(timeout=5).json()['status'] == 'ok'
