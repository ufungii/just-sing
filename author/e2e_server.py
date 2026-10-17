"""Disposable synthetic author fixture for the Playwright smoke test."""
import tempfile
import json
import wave
from pathlib import Path
import uvicorn
from .server import create_app, ROOT
from .test_author import seed
from .ingest import SongImports
from .test_ingest import fixture_process

if __name__ == '__main__':
    output = ROOT / 'ml/data/test-runs'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='author-browser-', dir=output) as folder:
        seed(Path(folder))
        long=Path(folder)/'long-song'
        long.mkdir()
        song=json.loads((Path(folder)/'test-song/song.json').read_text())
        song.update(id='long-song',title='Long synthetic song',duration=210)
        song['provenance']['crop_end']=210
        song['lines']=[{'start':i*3+1,'end':i*3+2.5,'text':f'Review line {i+1}',
                        'romanized':f'Review line {i+1}','translation':'','practice_text':'','words':[]} for i in range(70)]
        song['phrases']=[{'id':f'p{i+1}','line_index':i,'start':i*3+1,'end':i*3+2.5} for i in range(70)]
        song['reference']['hz']=[220]*10500
        (long/'song.json').write_text(json.dumps(song))
        for role in ('vocals','instrumental'):
            with wave.open(str(long/(role+'.wav')),'wb') as audio:
                audio.setparams((1,2,8000,0,'NONE','not compressed'))
                audio.writeframes(b'\x00\x00'*8000*210)
        uvicorn.run(create_app(Path(folder),imports=SongImports(Path(folder),processor=fixture_process)),host='127.0.0.1',port=8011)
