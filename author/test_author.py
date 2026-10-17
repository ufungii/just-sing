"""Synthetic fixtures only: no song lyrics, copyrighted media, or database."""
from copy import deepcopy
import json
from pathlib import Path
import wave

from fastapi.testclient import TestClient
import pytest

from author.server import create_app
from author.store import Store, write_json
from ml.pipeline.author_edits import validate_sections
from ml.pipeline.common import digest
from ml.pipeline.manifest import build_manifest


def seed(root):
    folder = root / 'test-song'
    folder.mkdir(parents=True)
    for role in ('vocals', 'instrumental'):
        with wave.open(str(folder / (role + '.wav')), 'wb') as out:
            out.setparams((1, 2, 8000, 0, 'NONE', 'not compressed'))
            out.writeframes(b'\x00\x00' * 8000 * 8)
    song = {'id': 'test-song', 'version': 1, 'title': 'Synthetic review fixture', 'artist': 'Test',
            'language': 'ko', 'duration': 8, 'audio': {r: r+'.wav' for r in ('vocals', 'instrumental')},
            'provenance': {'source_url': '', 'source_version': 'synthetic', 'crop_start': 0, 'crop_end': 8},
            'lines': [{'start': i*3+1, 'end': i*3+3, 'text': '\uc548\ub155', 'romanized': 'annyeong',
                       'translation': 'Hello', 'practice_text': '\uc548\ub155',
                       'words': [{'start': i*3+1, 'end': i*3+3, 'text': '\uc548\ub155'}]} for i in range(2)],
            'phrases': [{'id': 'p'+str(i+1), 'line_index': i, 'start': i*3+1, 'end': i*3+3} for i in range(2)],
            'reference': {'hop_seconds': .02, 'hz': [220]*400, 'notes': [], 'excluded': []}}
    write_json(folder / 'song.json', song)
    write_json(folder / 'corrections.json', {'source_audio_sha256': digest(folder/'vocals.wav'),
               'lyric_lines_sha256': 'existing-text-hash', 'line_starts': [1,4], 'unrelated': {'keep': True}})
    write_json(folder / 'song.review.json', {'reviewed': False, 'custom': 'preserved'})
    return Store(root)


def edited(store):
    loaded = store.load('test-song')
    song = deepcopy(loaded['song'])
    song['lines'][0]['start'] = 1.2
    song['lines'][0]['words'][0]['start'] = 1.2
    song['lines'][0]['translation'] = 'A greeting'
    song['phrases'][0]['start'] = 1.2
    song['phrases'][0]['end'] = 3.2
    song['reference']['excluded'] = [{'start': 7, 'end': 8, 'reason': 'Synthetic rest'}]
    song['duet_sections'] = [{'id':'first','slot':1,'phrase_ids':['p1']}, {'id':'second','slot':1,'phrase_ids':['p2']}]
    return loaded, song


def test_save_rebuild_review_and_backups(tmp_path):
    store = seed(tmp_path)
    before, song = edited(store)
    saved = store.save('test-song', song, before['revision'])
    folder = store.folder('test-song')
    assert json.loads((folder/'song.json').read_text())['lines'][0]['start'] == 1
    corrections = json.loads((folder/'corrections.json').read_text())
    assert corrections['unrelated'] == {'keep': True}
    assert corrections['line_starts'] == [1,4]
    assert corrections['lyric_lines_sha256'] == 'existing-text-hash'
    assert (folder/'corrections.json.bak').exists() and (folder/'song.review.json.bak').exists()
    assert 'author' not in json.loads((folder/'corrections.json.bak').read_text())
    with pytest.raises(ValueError, match='Rebuild'):
        store.mark_reviewed('test-song',saved['revision'])
    rebuilt = store.rebuild('test-song', saved['revision'])
    assert rebuilt['song']['lines'][0]['start'] == 1.2
    assert rebuilt['song']['lines'][0]['translation'] == 'A greeting'
    assert rebuilt['song']['phrases'][0]['end'] == 3.2
    assert rebuilt['song']['duet_sections'] == song['duet_sections']
    assert rebuilt['song']['reference']['excluded'] == song['reference']['excluded']
    assert (folder/'song.json.bak').exists()
    reviewed = store.mark_reviewed('test-song',rebuilt['revision'])
    assert reviewed['review']['reviewed'] is True
    assert reviewed['review']['custom'] == 'preserved'
    store.save('test-song', reviewed['song'], reviewed['revision'])
    assert store.load('test-song')['review']['reviewed'] is False


def test_pipeline_assembly_consumes_author_overrides(tmp_path):
    store = seed(tmp_path)
    initial, song = edited(store)
    folder = store.folder('test-song')
    write_json(folder/'preparation.json', initial['song'])
    (folder/'alignment').mkdir()
    hashes = store.hashes('test-song')
    write_json(folder/'alignment/lyrics.aligned.json', {'duration':8, 'lines':initial['song']['lines'],
               'source_audio_sha256':hashes['vocals'], 'instrumental_sha256':hashes['instrumental']})
    write_json(folder/'reference.pitch.json', {**song['reference'], 'duration':8,'source_audio_sha256':hashes['vocals']})
    store.save('test-song', song, store.load('test-song')['revision'])
    built, _ = build_manifest(folder)
    assert built['lines'][0]['start'] == 1.2 and built['phrases'][0]['end'] == 3.2
    assert built['duet_sections'] == song['duet_sections']
    assert built['lines'][0]['translation'] == 'A greeting'


def test_text_edit_regenerates_romanization_and_keeps_translation(tmp_path):
    store = seed(tmp_path)
    loaded = store.load('test-song')
    loaded['song']['lines'][0].update(text='\uac00\ub098', words=[])
    saved = store.save('test-song', loaded['song'], loaded['revision'])
    assert saved['song']['lines'][0]['romanized'] == 'gana'
    assert saved['song']['lines'][0]['translation'] == 'Hello'


@pytest.mark.parametrize('failure', ['unknown','duplicate','missing','slot','section','order','split'])
def test_invalid_ownership_rejected(failure):
    phrases = [{'id':'p1','line_index':0,'start':1,'end':2},{'id':'p2','line_index':1,'start':3,'end':4}]
    sections = [{'id':'s1','slot':0,'phrase_ids':['p1']},{'id':'s2','slot':1,'phrase_ids':['p2']}]
    if failure == 'unknown': sections[0]['phrase_ids']=['absent']
    if failure == 'duplicate': sections[1]['phrase_ids']=['p1']
    if failure == 'missing': sections.pop()
    if failure == 'slot': sections[0]['slot']=True
    if failure == 'section': sections[1]['id']='s1'
    if failure == 'order': sections.reverse()
    if failure == 'split': phrases[1]['line_index']=0
    with pytest.raises(ValueError): validate_sections(phrases,sections)


def test_stale_audio_revision_and_bad_times_rejected(tmp_path):
    store = seed(tmp_path)
    initial, song = edited(store)
    song['lines'][0]['start'] = float('nan')
    with pytest.raises(ValueError): store.save('test-song', song, initial['revision'])
    initial, song = edited(store)
    saved = store.save('test-song', song, initial['revision'])
    with pytest.raises(ValueError, match='changed'): store.save('test-song', song, initial['revision'])
    with (store.folder('test-song')/'vocals.wav').open('ab') as out: out.write(b'changed')
    with pytest.raises(ValueError, match='different audio'): store.load('test-song')


def test_local_routes_reject_remote_hosts_origins_and_paths(tmp_path):
    seed(tmp_path)
    client = TestClient(create_app(tmp_path), base_url='http://127.0.0.1:8010')
    assert len(client.get('/api/songs').json()) == 1
    assert client.get('/api/songs',headers={'host':'public.example'}).status_code == 403
    assert client.post('/api/songs/test-song/save',json={},headers={'origin':'https://evil.example'}).status_code == 403
    assert client.post('/api/songs/test-song/save',data='x').status_code == 403
    assert client.get('/api/songs/test-song/audio/vocals',headers={'Range':'bytes=0-31'}).status_code == 206
    assert client.get('/api/songs/test-song/audio/other').status_code == 422
    with pytest.raises(ValueError): Store(tmp_path).folder('../outside')
