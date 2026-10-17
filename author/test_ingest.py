"""Preparation orchestration with synthetic audio; inference is supplied by a fixture worker."""
from io import BytesIO
import json
from threading import Event
import time
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

from author.ingest import PreparationError, SongImports
from author.server import create_app
from author.test_author import seed


def upload(content=b'fixture audio', filename='recording.wav'):
    return SimpleNamespace(filename=filename, file=BytesIO(content))


def submit(manager, song_id='new-song', **kwargs):
    return manager.submit(kwargs.pop('audio', upload()), song_id, 'New song', 'Test artist',
                          'Hello world\nHello again', 'en')


def fixture_process(job, prepared):
    source = seed(prepared).folder('test-song')
    song = json.loads((source / 'song.json').read_text())
    song.update(id=job['song_id'], title=job['title'], artist=job['artist'], language=job['language'])
    (source / 'song.json').write_text(json.dumps(song))
    output = prepared / job['song_id']
    source.rename(output)
    return output


def finished(manager, job):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = manager.get(job['id'])
        if result['status'] in ('ready', 'failed', 'canceled') and manager.active is None:
            return result
        time.sleep(.01)
    pytest.fail('Preparation did not finish')


def test_new_song_is_private_until_complete_and_does_not_replace_existing(tmp_path):
    original = seed(tmp_path).load('test-song')
    entered, release = Event(), Event()
    def worker(job, prepared):
        entered.set()
        assert release.wait(5)
        return fixture_process(job, prepared)
    manager = SongImports(tmp_path, processor=worker)
    try:
        job = submit(manager)
        assert entered.wait(2)
        assert not (tmp_path / 'new-song').exists()
        with pytest.raises(PreparationError, match='Another song'):
            submit(manager, 'other-song')
        release.set()
        assert finished(manager, job)['status'] == 'ready'
        assert (tmp_path / 'new-song/song.json').is_file()
        assert seed_read(tmp_path, 'test-song') == original['song']
        assert not manager.get(job['id'])['cancel_requested']
        with pytest.raises(PreparationError, match='already exists'):
            submit(manager, 'new-song')
        with pytest.raises(PreparationError, match='already exists'):
            submit(manager, 'test-song')
    finally:
        release.set()
        manager.close()


def seed_read(root, song_id):
    return json.loads((root / song_id / 'song.json').read_text())


def test_failure_cleanup_retry_and_persistence(tmp_path):
    count = 0
    def worker(job, prepared):
        nonlocal count
        count += 1
        if count == 1:
            prepared.mkdir(parents=True)
            (prepared / 'partial.json').write_text('{}')
            raise RuntimeError('fixture inference failure')
        return fixture_process(job, prepared)
    manager = SongImports(tmp_path, processor=worker)
    try:
        job = submit(manager)
        assert finished(manager, job)['status'] == 'failed'
        assert not (tmp_path / 'new-song').exists()
        assert not (manager.folder(job['id']) / 'prepared').exists()
        assert (manager.folder(job['id']) / 'source.wav').is_file()
        assert finished(manager, manager.retry(job['id']))['status'] == 'ready'
    finally:
        manager.close()
    restarted = SongImports(tmp_path, processor=fixture_process)
    try:
        assert restarted.list()[0]['status'] == 'ready'
        assert restarted.list()[0]['id'] == job['id']
    finally:
        restarted.close()


def test_cancel_never_publishes_and_interrupted_jobs_can_be_retried(tmp_path):
    entered, release = Event(), Event()
    def worker(job, prepared):
        entered.set()
        assert release.wait(5)
        return fixture_process(job, prepared)
    manager = SongImports(tmp_path, processor=worker)
    try:
        job = submit(manager)
        assert entered.wait(2)
        assert manager.cancel(job['id'])['cancel_requested'] is True
        release.set()
        assert finished(manager, job)['status'] == 'canceled'
        assert not (tmp_path / 'new-song').exists()
        # Simulate durable metadata left by an abruptly stopped server.
        manager.update(job['id'], status='processing')
    finally:
        release.set()
        manager.close()
    restarted = SongImports(tmp_path, processor=fixture_process)
    try:
        assert restarted.get(job['id'])['status'] == 'failed'
        assert finished(restarted, restarted.retry(job['id']))['status'] == 'ready'
    finally:
        restarted.close()


def test_invalid_manifest_is_not_published(tmp_path):
    def worker(job, prepared):
        output = fixture_process(job, prepared)
        song = json.loads((output / 'song.json').read_text())
        song['phrases'][0]['end'] = 1000
        (output / 'song.json').write_text(json.dumps(song))
        return output
    manager = SongImports(tmp_path, processor=worker)
    try:
        job = submit(manager)
        assert finished(manager, job)['status'] == 'failed'
        assert not (tmp_path / 'new-song').exists()
    finally:
        manager.close()


def test_upload_routes_validate_ids_files_limits_and_keep_local_access(tmp_path, monkeypatch):
    manager = SongImports(tmp_path, processor=fixture_process)
    with TestClient(create_app(tmp_path, imports=manager), base_url='http://127.0.0.1:8010') as client:
        def post(song_id='new-song', content=b'fixture audio', filename='take.wav', headers=None):
            return client.post('/api/imports', data={'song_id': song_id, 'title': 'New song', 'artist': 'Test',
                               'lyrics': 'Hello world', 'language': 'en'}, files={'audio': (filename, content)}, headers=headers)
        assert client.get('/api/imports').json()['available'] is True
        assert post('../escape').status_code == 422
        assert post(filename='bad.exe').status_code == 422
        assert post(content=b'').status_code == 422
        assert post(headers={'origin':'https://outside.example'}).status_code == 403
        assert post(headers={'host':'public.example'}).status_code == 403
        monkeypatch.setattr('author.ingest.MAX_AUDIO_BYTES', 4)
        assert post(content=b'12345').status_code == 413
        monkeypatch.setattr('author.ingest.MAX_AUDIO_BYTES', 250 * 1024 * 1024)
        response = post()
        assert response.status_code == 202
        result = finished(manager, response.json())
        assert result['status'] == 'ready'
        assert client.get('/api/imports/' + result['id']).json()['song_id'] == 'new-song'
        assert any(song['id'] == 'new-song' for song in client.get('/api/songs').json())
        assert post().status_code == 409


def test_missing_processing_environment_is_actionable(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTHOR_PIPELINE_PYTHON', str(tmp_path / 'missing-python'))
    monkeypatch.setenv('AUTHOR_SEPARATION_PYTHON', str(tmp_path / 'missing-separation-python'))
    manager = SongImports(tmp_path)
    try:
        assert manager.availability()['available'] is False
        with pytest.raises(PreparationError, match='environments configured') as error:
            submit(manager)
        assert error.value.status == 503
        assert manager.list() == []
    finally:
        manager.close()
