"""Explicit, backed-up edits and rebuilds for prepared local songs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil

from ml.pipeline.author_edits import apply_author_edits
from ml.pipeline.common import digest, read
from ml.pipeline.text import korean_practice_text


def write_json(path, data):
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + '.bak'))
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def folder(self, song_id):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', song_id):
            raise ValueError('Invalid song ID')
        folder = (self.root / song_id).resolve()
        if not folder.is_relative_to(self.root) or not (folder / 'song.json').is_file():
            raise ValueError('Prepared song not found')
        return folder

    def revision(self, folder):
        return hashlib.sha256(b''.join((folder / name).read_bytes() if (folder / name).exists() else b''
                                     for name in ('song.json', 'corrections.json', 'song.review.json'))).hexdigest()

    def audio(self, song_id, role):
        if role not in ('vocals', 'instrumental'):
            raise ValueError('Unknown audio role')
        folder = self.folder(song_id)
        path = (folder / read(folder / 'song.json')['audio'][role]).resolve()
        if not path.is_relative_to(folder) or not path.is_file():
            raise ValueError('Audio must exist inside its song directory')
        return path

    def hashes(self, song_id):
        return {role: digest(self.audio(song_id, role)) for role in ('vocals', 'instrumental')}

    def catalog(self):
        songs = []
        for folder in sorted(self.root.glob('*')):
            if (folder / 'song.json').is_file():
                try:
                    song = read(self.folder(folder.name) / 'song.json')
                    songs.append({key: song[key] for key in ('id', 'title', 'artist', 'duration')})
                except (ValueError, KeyError, OSError):
                    continue
        return songs

    def load(self, song_id):
        folder = self.folder(song_id)
        corrections = read(folder / 'corrections.json') if (folder / 'corrections.json').exists() else {}
        song = apply_author_edits(read(folder / 'song.json'), corrections.get('author'), self.hashes(song_id))
        review = read(folder / 'song.review.json') if (folder / 'song.review.json').exists() else {}
        return {'song': song, 'review': review, 'revision': self.revision(folder)}

    def check_revision(self, folder, revision):
        if revision != self.revision(folder):
            raise ValueError('Files changed since loading. Reload before saving; your edits were not written.')

    def save(self, song_id, song, revision):
        folder = self.folder(song_id)
        self.check_revision(folder, revision)
        original = read(folder / 'song.json')
        if song['id'] != song_id or [p['id'] for p in song['phrases']] != [p['id'] for p in original['phrases']]:
            raise ValueError('Song and phrase IDs cannot change')
        from ml.pipeline.romanize import romanize_text
        lines = deepcopy(song['lines'])
        for line in lines:
            line['romanized'] = romanize_text(line['text'])
            line['practice_text'] = korean_practice_text(line['text'])
        edits = {'schema_version': 1, 'audio_sha256': self.hashes(song_id), 'lines': lines,
                 'phrases': song['phrases'], 'phrase_ids': [p['id'] for p in song['phrases']],
                 'excluded': song['reference']['excluded'], 'duet_sections': song.get('duet_sections')}
        apply_author_edits(original, edits, edits['audio_sha256'])
        corrections = read(folder / 'corrections.json') if (folder / 'corrections.json').exists() else {}
        corrections['author'] = edits
        review = read(folder / 'song.review.json') if (folder / 'song.review.json').exists() else {}
        review.update(reviewed=False, status='draft', author_pending_rebuild=True)
        # Invalidate review before changing corrections. A partial failure stays draft.
        write_json(folder / 'song.review.json', review)
        write_json(folder / 'corrections.json', corrections)
        return self.load(song_id)

    def rebuild(self, song_id, revision):
        folder = self.folder(song_id)
        self.check_revision(folder, revision)
        if (folder / 'preparation.json').is_file():
            from ml.pipeline.manifest import build_manifest
            song, generated_review = build_manifest(folder)
        else:
            # Portable handoffs embed all cached content in song.json.
            song, generated_review = read(folder / 'song.json'), {}
        corrections = read(folder / 'corrections.json') if (folder / 'corrections.json').exists() else {}
        song = apply_author_edits(song, corrections.get('author'), self.hashes(song_id))
        review = read(folder / 'song.review.json') if (folder / 'song.review.json').exists() else {}
        review.update(generated_review)
        review.update(reviewed=False, status='draft', author_pending_rebuild=True)
        write_json(folder / 'song.review.json', review)
        write_json(folder / 'song.json', song)
        review.update(manifest_sha256=digest(folder / 'song.json'), audio_sha256=self.hashes(song_id),
                      author_pending_rebuild=False)
        write_json(folder / 'song.review.json', review)
        return self.load(song_id)

    def mark_reviewed(self, song_id, revision):
        folder = self.folder(song_id)
        self.check_revision(folder, revision)
        review = read(folder / 'song.review.json')
        if review.get('author_pending_rebuild') or review.get('manifest_sha256') != digest(folder / 'song.json'):
            raise ValueError('Rebuild saved corrections before marking reviewed')
        if review.get('audio_sha256') != self.hashes(song_id):
            raise ValueError('Audio changed since rebuild')
        review.update(reviewed=True, status='reviewed', lyrics_reviewed=True, phrases_reviewed=True,
                      reference_reviewed=True, translations_reviewed=True)
        write_json(folder / 'song.review.json', review)
        return self.load(song_id)
