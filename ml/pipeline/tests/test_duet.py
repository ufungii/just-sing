import hashlib
import unittest

from ..duet import section_plan, assign_sections, rebase_plan, balanced_sections


class DuetSectionsTest(unittest.TestCase):
    def setUp(self):
        self.track = {'section_starts': [0, 4, 8], 'lines': [
            {'text': f'line {i}', 'start': i * 3, 'end': i * 3 + 2} for i in range(12)]}
        self.phrases = [{'id': f'p{i}', 'line_index': i, 'start': i * 3, 'end': i * 3 + 2} for i in range(12)]

    def test_whole_stanzas_instead_of_three_line_fallback(self):
        sections, fallback = assign_sections(self.phrases, section_plan(self.track))
        self.assertEqual([s['slot'] for s in sections], [0, 1, 0])
        self.assertEqual(sections[0]['phrase_ids'], ['p0', 'p1', 'p2', 'p3'])
        self.assertFalse(fallback)

    def test_empty_unscoreable_section_does_not_shift_later_singers(self):
        sections, _ = assign_sections([p for p in self.phrases if p['line_index'] >= 4], section_plan(self.track))
        self.assertEqual([s['slot'] for s in sections], [1, 0])

    def test_crop_keeps_parent_ids_and_slots(self):
        plan = rebase_plan(self.track, section_plan(self.track), 15, 33)
        self.assertEqual(plan, [{'id': 'section-2', 'line_index': 0, 'slot': 1},
                                {'id': 'section-3', 'line_index': 3, 'slot': 0}])

    def test_short_one_verse_demo_uses_one_complete_line_handoff(self):
        phrases = self.phrases[:4] + [{**self.phrases[3], 'id': 'p3b', 'start': 11, 'end': 11.5}]
        sections, fallback = assign_sections(phrases, section_plan(self.track), short_clip=True)
        self.assertTrue(fallback)
        self.assertEqual([s['slot'] for s in sections], [0, 1])
        self.assertIn('p3', sections[1]['phrase_ids'])
        self.assertIn('p3b', sections[1]['phrase_ids'])

    def test_full_song_does_not_invent_mid_verse_switches(self):
        sections, fallback = assign_sections(self.phrases[:4], section_plan(self.track))
        self.assertEqual(len(sections), 1)
        self.assertFalse(fallback)

    def test_override_is_bound_to_text_and_rejects_invalid_boundaries(self):
        override = {'lyric_lines_sha256': hashlib.sha256('\n'.join(l['text'] for l in self.track['lines']).encode()).hexdigest(),
                    'section_starts': [0, 8], 'starting_slot': 1}
        self.assertEqual([s['slot'] for s in section_plan(self.track, override)], [1, 0])
        for bad in ([0, 8, 4], [4, 8], [0, 12], [0, True], [0, 4, 4]):
            with self.assertRaises(ValueError):section_plan(self.track, {**override, 'section_starts': bad})
        with self.assertRaises(ValueError):section_plan(self.track, {**override, 'lyric_lines_sha256': 'stale'})

    def test_cropped_single_singer_keeps_owner_when_no_fallback_is_needed(self):
        plan = [{'id': 'verse-2', 'slot': 1, 'line_index': 0}]
        sections, fallback = assign_sections(self.phrases[:1], plan, short_clip=True)
        self.assertEqual(sections[0]['slot'], 1)
        self.assertFalse(fallback)

    def test_each_verse_and_chorus_gets_two_equal_halves(self):
        weights = {p['id']: 2 for p in self.phrases}
        sections, report = balanced_sections(self.phrases, section_plan(self.track), weights)
        self.assertEqual(len(sections), 6)
        for index in range(3):
            pair = sections[2 * index:2 * index + 2]
            self.assertEqual({s['slot'] for s in pair}, {0, 1})
            self.assertEqual(report[index]['scoreable_seconds'], [4, 4])

    def test_balance_uses_voiced_time_and_keeps_split_line_phrases_together(self):
        phrases = self.phrases[:4] + [{**self.phrases[3], 'id': 'p3b', 'start': 11, 'end': 11.5}]
        weights = dict(p0=6, p1=2, p2=2, p3=1, p3b=1)
        sections, _ = balanced_sections(phrases, section_plan(self.track), weights)
        self.assertEqual(sections[0]['phrase_ids'], ['p0'])
        self.assertEqual(sections[1]['phrase_ids'], ['p1', 'p2', 'p3', 'p3b'])

    def test_unequal_line_lengths_balance_across_sections_deterministically(self):
        weights = {p['id']: (3 if p['line_index'] % 4 == 0 else 2) for p in self.phrases}
        sections, report = balanced_sections(self.phrases, section_plan(self.track), weights)
        self.assertEqual([r['difference_seconds'] for r in report], [1, 1, 1])
        totals = [sum(weights[pid] for s in sections if s['slot'] == slot for pid in s['phrase_ids']) for slot in (0, 1)]
        self.assertEqual(abs(totals[0] - totals[1]), 1)
        self.assertEqual((sections, report), balanced_sections(self.phrases, section_plan(self.track), weights))

    def test_single_line_section_is_reported_without_splitting_the_line(self):
        sections, report = balanced_sections(self.phrases[:1], section_plan(self.track), {'p0': 2})
        self.assertEqual(len(sections), 1)
        self.assertFalse(report[0]['both_players'])
