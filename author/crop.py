"""Create a separate portable clip from either a prepared folder or a Drive handoff."""
from copy import deepcopy
import json
from math import ceil, floor, isfinite
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from ml.pipeline.crop import rebase_lines
from ml.pipeline.common import digest


def crop_song(store, source_id, destination_id, title, start, end, revision):
    from api.models import Song
    source = store.folder(source_id)
    store.check_revision(source, revision)
    loaded = store.load(source_id)
    source_hashes = store.hashes(source_id)
    if loaded['review'].get('author_pending_rebuild'):
        raise ValueError('Rebuild saved edits before creating a short clip.')
    if not isinstance(destination_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', destination_id):
        raise ValueError('Choose a new clip ID with letters, digits, hyphens or underscores.')
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError('Enter a clip title under 200 characters.')
    destination = store.root / destination_id
    if destination.exists():
        raise ValueError('That song ID already exists. Choose a new ID to preserve it.')
    song = loaded['song']
    Song.model_validate(song)
    if (isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, (int,float)) or not isinstance(end, (int,float))
            or not isfinite(start) or not isfinite(end) or not 0 <= start < end <= song['duration']):
        raise ValueError('Choose finite crop bounds inside the song.')
    ffmpeg = shutil.which('ffmpeg')
    if not ffmpeg:
        raise ValueError('Install FFmpeg on this computer before saving short clips.')
    first, last = round(start * 44100), round(end * 44100)
    start, end = first / 44100, last / 44100
    duration = (last-first) / 44100
    if duration < .02:
        raise ValueError('Select at least 0.02 seconds.')
    lines, partial, _ = rebase_lines({'lines':song['lines']}, start, end)
    indices = [i for i,line in enumerate(song['lines']) if line['end']>start and line['start']<end]
    mapping = {old:new for new,old in enumerate(indices)}
    phrases = [{**p,'line_index':mapping[p['line_index']], 'start':max(0,round(p['start']-start,6)),
                'end':min(duration,round(p['end']-start,6))} for p in song['phrases']
               if p['line_index'] in mapping and mapping[p['line_index']] not in partial
               and p['start']>=start-1e-6 and p['end']<=end+1e-6]
    if not phrases:
        raise ValueError('Include at least one complete scored lyric line. Partial boundary lines are display-only.')
    reference = deepcopy(song['reference'])
    hop = reference['hop_seconds']
    source_hz = reference['hz']
    if not isfinite(hop) or hop<=0 or not source_hz:
        raise ValueError('The source song has no usable reference pitch grid.')
    reference['hz'] = [source_hz[min(len(source_hz)-1,floor((start+i*hop)/hop+.5+1e-9))]
                       for i in range(ceil(duration/hop))]
    for field in ('notes','excluded'):
        reference[field] = [{**item,'start':max(0,round(item['start']-start,6)),
                             'end':min(duration,round(item['end']-start,6))}
                            for item in reference[field] if item['end']>start and item['start']<end]
    result = {**deepcopy(song), 'id':destination_id, 'version':1, 'title':title.strip(), 'duration':duration,
              'audio':{role:role+'.mp3' for role in ('vocals','instrumental')}, 'lines':lines,
              'phrases':phrases,'reference':reference}
    result['provenance']['crop_start'] = song['provenance']['crop_start']+start
    result['provenance']['crop_end'] = result['provenance']['crop_start']+duration
    if song.get('duet_sections') is not None:
        keep = {p['id'] for p in phrases}
        result['duet_sections'] = [{**section,'phrase_ids':[pid for pid in section['phrase_ids'] if pid in keep]}
                                   for section in song['duet_sections'] if any(pid in keep for pid in section['phrase_ids'])]
    Song.model_validate(result)
    staging = store.root / '.cropping'
    staging.mkdir(exist_ok=True)
    if not staging.resolve().is_relative_to(store.root):
        raise ValueError('Crop workspace must stay inside the song data folder.')
    with tempfile.TemporaryDirectory(prefix=destination_id+'-',dir=staging) as temporary:
        output = Path(temporary) / destination_id
        output.mkdir()
        for role in ('vocals','instrumental'):
            try:
                subprocess.run([ffmpeg,'-nostdin','-v','error','-n','-i',str(store.audio(source_id,role)),
                                '-af',f'aresample=44100,atrim=start_sample={first}:end_sample={last},asetpts=PTS-STARTPTS',
                                '-ar','44100','-ac','2','-c:a','libmp3lame','-b:a','320k',str(output/(role+'.mp3'))],
                               check=True,capture_output=True,timeout=180)
                decoded = subprocess.run([ffmpeg,'-nostdin','-v','error','-i',str(output/(role+'.mp3')),
                                          '-ar','44100','-ac','1','-f','s16le','-'],
                                         check=True,capture_output=True,timeout=60)
                if len(decoded.stdout)//2 != last-first:
                    raise ValueError('The source audio is shorter than the requested crop.')
            except (subprocess.SubprocessError,OSError) as error:
                raise ValueError('Could not create the cropped audio. Check the source stems and try again.') from error
        (output/'song.json').write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2)+'\n')
        hashes = {role:digest(output/(role+'.mp3')) for role in ('vocals','instrumental')}
        review = {'reviewed':False,'status':'draft','author_pending_rebuild':False,
                  'manifest_sha256':digest(output/'song.json'),'audio_sha256':hashes,
                  'notes':'New clip copied from a parent draft; partial boundary lines are display-only. Listen and review the rebased lyrics and pitch.'}
        (output/'song.review.json').write_text(json.dumps(review,indent=2)+'\n')
        (output/'crop.source.json').write_text(json.dumps({'id':source_id,'version':song['version'],
            'range':{'start':start,'end':end},'audio_sha256':source_hashes},indent=2)+'\n')
        # A source edit or another writer must not produce a stale or overwritten clip.
        store.check_revision(source,revision)
        if store.hashes(source_id)!=source_hashes:
            raise ValueError('Source audio changed while cropping. Reload the song and try again.')
        if destination.exists():
            raise ValueError('That clip ID was just created. Choose a new ID.')
        output.rename(destination)
    return store.load(destination_id)
