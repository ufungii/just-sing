"""Shared player-name policy; no model or database dependency."""
import json
from pathlib import Path
import re
import unicodedata

_POLICY = json.loads((Path(__file__).resolve().parents[1] / 'contracts/player-name-policy.json').read_text())


def _normalize(name):
    text = ''.join(ch for ch in unicodedata.normalize('NFKD', name)
                   if unicodedata.category(ch) not in ('Mn', 'Mc', 'Me', 'Cf'))
    return ' '.join(text.lower().split())


def _words(text):
    return re.findall('[a-z0-9]+', text)


def _pattern(term):
    compact = ''.join(_words(term))
    groups = [match.group() for match in re.finditer(r'(.)\1*', compact)]
    return re.compile('^' + ''.join(re.escape(run[0]) + '{' + str(len(run)) + ',}' for run in groups) + '$')


_JOKES = {_normalize(name) for name in _POLICY['joke_names']}
_BLOCKED = [_pattern(term) for term in _POLICY['blocked_terms']]


def blocked_player_name_reason(name: str) -> str | None:
    normalized = _normalize(name)
    without_trailing_numbers = re.sub(r'[0-9]+(?=[^a-z0-9]|$)', '', normalized)
    variants = [value for base in (normalized, without_trailing_numbers)
                for value in (base, re.sub(r'(^|[^a-z0-9])[0-9]+', r'\1', base))]
    candidates = []
    for variant in variants:
        decoded = ''.join(_POLICY['substitutions'].get(ch, ch) for ch in variant)
        tokens = _words(decoded)
        candidates.extend(tokens + [''.join(tokens)])
        run = ''
        for token in tokens + ['']:
            if len(token) == 1:
                run += token
            else:
                if run:
                    candidates.append(run)
                run = ''
    if any(pattern.fullmatch(candidate) for candidate in candidates for pattern in _BLOCKED):
        return 'language'
    return 'joke' if normalized in _JOKES else None


def validate_player_name(name: str) -> str:
    name = name.strip()
    if not name or len(name) > 40 or blocked_player_name_reason(name):
        raise ValueError('Choose a different player name.')
    return name
