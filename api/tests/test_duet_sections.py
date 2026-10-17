"""Duet ownership is authored once on whole lyric lines; legacy manifests still load."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.duets import sections, timed_sections
from api.models import Song


@pytest.fixture
def manifest():
    return json.loads((Path(__file__).parents[1] / 'catalog/duet-demo/song.json').read_text())


def test_explicit_slots_can_repeat_and_start_with_player_two(manifest):
    for section, slot in zip(manifest['duet_sections'], (1, 1, 0)):
        section['slot'] = slot
    assert [s.slot for s in sections(Song.model_validate(manifest))] == [1, 1, 0]


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'unknown', 'order', 'slot', 'section_id', 'split_line', 'overlap'])
def test_invalid_sections_are_rejected(manifest, problem):
    s = manifest['duet_sections']
    if problem == 'missing': s[-1]['phrase_ids'].pop()
    elif problem == 'duplicate': s[-1]['phrase_ids'].append('d1')
    elif problem == 'unknown': s[-1]['phrase_ids'][-1] = 'unknown'
    elif problem == 'order': s.reverse()
    elif problem == 'slot': s[0]['slot'] = 2
    elif problem == 'section_id': s[1]['id'] = s[0]['id']
    elif problem == 'split_line': manifest['phrases'][3]['line_index'] = 0
    elif problem == 'overlap': manifest['phrases'][3]['start'] = 8.0
    with pytest.raises(ValidationError): Song.model_validate(manifest)


def test_legacy_fallback_groups_three_scored_lines_without_renumbering_a_range(manifest):
    del manifest['duet_sections']
    song = Song.model_validate(manifest)
    assert [(s.slot, s.phrase_ids) for s in sections(song)] == [
        (0, ['d1', 'd2', 'd3']), (1, ['d4', 'd5', 'd6']), (0, ['d7', 'd8', 'd9'])]
    clipped = timed_sections(song, {'d4', 'd5', 'd6', 'd7'})
    assert [s['slot'] for s in clipped] == [1, 0]
    assert clipped[0]['start'] == 9 and clipped[-1]['end'] == 20.5


def test_contract_duet_example_matches_model():
    path = Path(__file__).parents[2] / 'contracts/duet-song.example.json'
    assert len(Song.model_validate_json(path.read_text()).duet_sections) == 3
