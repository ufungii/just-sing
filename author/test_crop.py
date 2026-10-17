import shutil

from fastapi.testclient import TestClient
import pytest

from author.crop import crop_song
from author.server import create_app
from author.test_author import seed

pytestmark=pytest.mark.skipif(not shutil.which('ffmpeg'),reason='needs FFmpeg')


def test_portable_song_crop_rebases_data_preserves_source_and_authored_ownership(tmp_path):
    store=seed(tmp_path)
    loaded=store.load('test-song')
    song=loaded['song']
    song['duet_sections']=[{'id':'first','slot':1,'phrase_ids':['p1']},{'id':'second','slot':0,'phrase_ids':['p2']}]
    saved=store.save('test-song',song,loaded['revision'])
    original=store.rebuild('test-song',saved['revision'])
    original_bytes=(store.folder('test-song')/'song.json').read_bytes()
    result=crop_song(store,'test-song','short-demo','My short clip',.5,5.5,original['revision'])
    clip=result['song']
    assert clip['id']=='short-demo' and clip['title']=='My short clip' and clip['duration']==5
    assert clip['phrases']==[{'id':'p1','line_index':0,'start':.5,'end':2.5}]
    assert clip['lines'][1]['practice_text']==''
    assert clip['duet_sections']==[{'id':'first','slot':1,'phrase_ids':['p1']}]
    assert len(clip['reference']['hz'])==250
    assert result['review']['reviewed'] is False
    assert (store.folder('test-song')/'song.json').read_bytes()==original_bytes
    assert store.load('test-song')['revision']==original['revision']
    assert (store.folder('short-demo')/'crop.source.json').is_file()
    for role in ('vocals','instrumental'):
        assert store.audio('short-demo',role).is_file()
    with pytest.raises(ValueError,match='already exists'):
        crop_song(store,'test-song','short-demo','Duplicate',1,3,original['revision'])


@pytest.mark.parametrize('start,end',[(0,.2),(4,3),(-1,4),(0,10),(float('nan'),4)])
def test_invalid_or_unscoreable_crop_never_creates_catalog_entry(tmp_path,start,end):
    store=seed(tmp_path)
    with pytest.raises(ValueError):
        crop_song(store,'test-song','bad-clip','Bad clip',start,end,store.load('test-song')['revision'])
    assert not (tmp_path/'bad-clip').exists()


def test_crop_route_requires_current_saved_and_rebuilt_source(tmp_path):
    store=seed(tmp_path)
    loaded=store.load('test-song')
    client=TestClient(create_app(tmp_path),base_url='http://127.0.0.1:8010')
    body={'id':'new-clip','title':'New clip','start':1,'end':6,'revision':loaded['revision']}
    assert client.post('/api/songs/test-song/crop',json={**body,'revision':'stale'}).status_code==422
    saved=store.save('test-song',loaded['song'],loaded['revision'])
    assert client.post('/api/songs/test-song/crop',json={**body,'revision':saved['revision']}).status_code==422
    rebuilt=store.rebuild('test-song',saved['revision'])
    response=client.post('/api/songs/test-song/crop',json={**body,'revision':rebuilt['revision']})
    assert response.status_code==200
    assert response.json()['song']['id']=='new-clip'
