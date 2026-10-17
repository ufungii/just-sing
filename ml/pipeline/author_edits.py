"""Validated, absolute author overrides layered over cached pipeline output.

The namespaced key leaves aligner's audio/text-bound anchors and other correction
metadata intact. Phrase IDs stay stable; line insertion/deletion is not supported.
"""
from copy import deepcopy
from math import isfinite


def interval(value, duration):
    start, end = value['start'], value['end']
    if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not isfinite(t) for t in (start, end)):
        raise ValueError('Times must be finite numbers')
    if not 0 <= start < end <= duration:
        raise ValueError('Times must satisfy 0 <= start < end <= duration')


def validate_sections(phrases, sections):
    if sections is None:
        return
    ordered = sorted(phrases, key=lambda p: (p['start'], p['end'], p['id']))
    if [pid for section in sections for pid in section['phrase_ids']] != [p['id'] for p in ordered]:
        raise ValueError('Assign every scored phrase exactly once, in chronological order')
    seen, lines, previous = set(), {}, 0
    by_id = {p['id']: p for p in phrases}
    for section in sections:
        if not isinstance(section['id'], str) or not section['id'] or section['id'] in seen:
            raise ValueError('Section IDs must be nonempty and unique')
        seen.add(section['id'])
        if type(section['slot']) is not int or section['slot'] not in (0, 1) or not section['phrase_ids']:
            raise ValueError('Each section needs Player 1 or Player 2 and at least one phrase')
        assigned = [by_id[pid] for pid in section['phrase_ids']]
        if assigned[0]['start'] < previous:
            raise ValueError('Duet sections must not overlap')
        previous = max(p['end'] for p in assigned)
        for phrase in assigned:
            if lines.setdefault(phrase['line_index'], section['id']) != section['id']:
                raise ValueError('A lyric line cannot be split between sections')


def apply_author_edits(manifest, edits, hashes):
    if not edits:
        return manifest
    if edits.get('audio_sha256') != hashes:
        raise ValueError('Author corrections belong to different audio')
    if edits.get('schema_version') != 1:
        raise ValueError('Unsupported author corrections version')
    result = deepcopy(manifest)
    lines, phrases = edits['lines'], edits['phrases']
    if len(lines) != len(result['lines']):
        raise ValueError('Author corrections require the same lyric line count')
    # Validate IDs against the cached snapshot recorded at Save. Filtering in
    # assembly can remove a short draft phrase before its held end is corrected.
    expected = edits['phrase_ids']
    if len(set(expected)) != len(expected) or [p['id'] for p in phrases] != expected:
        raise ValueError('Phrase IDs changed in author corrections')
    previous = 0
    for index, line in enumerate(lines):
        interval(line, result['duration'])
        if line['start'] < previous or not isinstance(line['text'], str) or not line['text'].strip():
            raise ValueError('Lyric lines must be nonempty and not overlap')
        previous = line['end']
        for key in ('romanized', 'translation', 'practice_text'):
            if not isinstance(line[key], str):
                raise ValueError('Lyric fields must be text')
        word_end = line['start']
        for word in line.get('words', []):
            interval(word, result['duration'])
            if not word_end <= word['start'] < word['end'] <= line['end'] or not word['text'].strip():
                raise ValueError('Words must be ordered inside their line')
            word_end = word['end']
    previous = 0
    for phrase in phrases:
        interval(phrase, result['duration'])
        if type(phrase['line_index']) is not int or not 0 <= phrase['line_index'] < len(lines):
            raise ValueError('Phrase points to a missing line')
        if phrase['start'] < previous:
            raise ValueError('Scored phrases must be chronological and not overlap')
        previous = phrase['end']
    for region in edits['excluded']:
        interval(region, result['duration'])
        if not isinstance(region['reason'], str) or not region['reason'].strip():
            raise ValueError('Excluded regions need a reason')
    validate_sections(phrases, edits.get('duet_sections'))
    result['lines'], result['phrases'] = deepcopy(lines), deepcopy(phrases)
    result['reference']['excluded'] = deepcopy(edits['excluded'])
    if edits.get('duet_sections') is None:
        result.pop('duet_sections', None)
    else:
        result['duet_sections'] = deepcopy(edits['duet_sections'])
    return result
