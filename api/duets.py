"""Manifest section ownership, independent of HTTP, database state and player names."""
from .models import DuetSection, Song


def metadata(value) -> dict | None:
    """Pending attempts use an object; accepted rows retain frozen settings on the first phrase."""
    return value.get('duet') if isinstance(value, dict) else value[0].get('_duet') if isinstance(value, list) and value else None


def sections(song: Song) -> list[DuetSection]:
    if song.duet_sections is not None:
        return song.duet_sections
    phrases = sorted(song.phrases, key=lambda p: (p.start, p.end, p.id))
    lines = list(dict.fromkeys(p.line_index for p in phrases))
    return [DuetSection(id=f'lines-{i + 1}', slot=(i // 3) % 2,
                       phrase_ids=[p.id for p in phrases if p.line_index in lines[i:i + 3]])
            for i in range(0, len(lines), 3)]


def timed_sections(song: Song, included_ids: set[str]) -> list[dict]:
    by_id = {p.id: p for p in song.phrases}
    result = []
    for section in sections(song):
        ids = [pid for pid in section.phrase_ids if pid in included_ids]
        if ids:
            result.append({**section.model_dump(), 'phrase_ids': ids,
                           'start': min(by_id[pid].start for pid in ids),
                           'end': max(by_id[pid].end for pid in ids)})
    return result
