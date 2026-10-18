"""Stable section ownership for continuous 1v1, authored on lyric-line boundaries."""
from bisect import bisect_right
import hashlib

from .author_edits import validate_sections


def balanced_sections(phrases, plan, weights):
    """Give both singers contiguous halves of each musical section.

    Weights are voiced, non-excluded seconds per phrase. Keep every phrase of
    a lyric line together, choose the closest half, then choose which singer
    starts each section to minimize the whole clip's remaining imbalance.
    """
    ordered = sorted(phrases, key=lambda p: (p['start'], p['end'], p['id']))
    starts = [s['line_index'] for s in plan]
    blocks = []
    for index, section in enumerate(plan):
        members = [p for p in ordered if bisect_right(starts, p['line_index']) - 1 == index]
        if not members:
            continue
        lines = list(dict.fromkeys(p['line_index'] for p in members))
        total = sum(weights[p['id']] for p in members)
        if len(lines) > 1:
            boundary = min(lines[1:], key=lambda line: (
                abs(2 * sum(weights[p['id']] for p in members if p['line_index'] < line) - total), line))
            halves = [[p for p in members if (p['line_index'] >= boundary) == bool(i)] for i in range(2)]
        else:
            halves = [members]
        seconds = [sum(weights[p['id']] for p in half) for half in halves]
        blocks.append((section['id'], halves, seconds))
    # Millisecond integer states keep the search deterministic and bounded by
    # clip duration, without a greedy choice trapping later sections.
    states = {0: ()}
    for _, halves, seconds in blocks:
        difference = round(1000 * (seconds[0] - (seconds[1] if len(halves) == 2 else 0)))
        following = {}
        for balance, owners in states.items():
            for first in (0, 1):
                key = balance + (difference if first == 0 else -difference)
                following.setdefault(key, owners + (first,))
        states = following
    owners = min(states.items(), key=lambda item: (abs(item[0]), item[1]))[1]
    result, report = [], []
    for (section_id, halves, seconds), first in zip(blocks, owners):
        totals = [0., 0.]
        for i, half in enumerate(halves):
            slot = (first + i) % 2
            totals[slot] += seconds[i]
            result.append({'id': f'{section_id}-half-{i + 1}', 'slot': slot,
                           'phrase_ids': [p['id'] for p in half]})
        report.append({'id': section_id, 'scoreable_seconds': totals,
                       'both_players': len(halves) == 2,
                       'difference_seconds': abs(totals[0] - totals[1])})
    validate_sections(phrases, result)
    return result, report


def section_plan(track, override=None):
    """Prefer a saved per-song plan, otherwise use the supplied stanza breaks."""
    count = len(track['lines'])
    if override is not None:
        expected = hashlib.sha256('\n'.join(line['text'] for line in track['lines']).encode()).hexdigest()
        if override.get('lyric_lines_sha256') != expected:
            raise ValueError('Duet plan belongs to different lyric lines')
        starts = override['section_starts']
        first = override.get('starting_slot', 0)
        if type(first) is not int or first not in (0, 1):
            raise ValueError('Duet starting slot must be 0 or 1')
        plan = [{'id': f'section-{i + 1}', 'line_index': start, 'slot': (first + i) % 2}
                for i, start in enumerate(starts)]
    elif 'duet_plan' in track:
        plan = track['duet_plan']
    else:
        plan = [{'id': f'section-{i + 1}', 'line_index': start, 'slot': i % 2}
                for i, start in enumerate(track.get('section_starts') or [0])]
    starts = [s['line_index'] for s in plan]
    if (not starts or starts[0] != 0 or any(type(i) is not int or not 0 <= i < count for i in starts)
            or starts != sorted(set(starts)) or len({s['id'] for s in plan}) != len(plan)
            or any(not isinstance(s['id'], str) or not s['id'] or type(s['slot']) is not int or s['slot'] not in (0, 1) for s in plan)):
        raise ValueError('Duet boundaries must start at line zero and increase through existing lines')
    return plan


def rebase_plan(track, plan, start, end):
    """A crop keeps the parent section IDs and singers, including mid-verse crops."""
    starts = [s['line_index'] for s in plan]
    result, child_index = [], 0
    for index, line in enumerate(track['lines']):
        if line['end'] <= start or line['start'] >= end:
            continue
        section = plan[bisect_right(starts, index) - 1]
        if not result or result[-1]['id'] != section['id']:
            result.append({**section, 'line_index': child_index})
        child_index += 1
    return result


def assign_sections(phrases, plan, *, short_clip=False):
    """Never split a phrase/line or renumber slots when empty sections are skipped."""
    ordered = sorted(phrases, key=lambda p: (p['start'], p['end'], p['id']))
    starts = [s['line_index'] for s in plan]
    result = []
    for index, section in enumerate(plan):
        ids = [p['id'] for p in ordered if bisect_right(starts, p['line_index']) - 1 == index]
        if ids:
            result.append({'id': section['id'], 'slot': section['slot'], 'phrase_ids': ids})
    fallback = False
    line_indices = list(dict.fromkeys(p['line_index'] for p in ordered))
    if short_clip and len({s['slot'] for s in result}) == 1 and len(line_indices) >= 2:
        # A demo wholly inside one verse must still give both singers a turn.
        # Choose one complete-line boundary near its midpoint, once at prep time.
        middle = (ordered[0]['start'] + ordered[-1]['end']) / 2
        boundary = min(line_indices[1:], key=lambda i: (abs(next(p['start'] for p in ordered if p['line_index'] == i) - middle), i))
        first = result[0]['slot']
        result = [{'id': f'demo-half-{i + 1}', 'slot': (first + i) % 2,
                   'phrase_ids': [p['id'] for p in ordered if (p['line_index'] >= boundary) == bool(i)]}
                  for i in range(2)]
        fallback = True
    validate_sections(phrases, result)
    return result, fallback
