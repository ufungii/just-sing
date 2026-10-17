import policy from '../../../contracts/player-name-policy.json';

export type BlockedNameReason = 'joke' | 'language';

function normalize(name: string): string {
  return name.normalize('NFKD').replace(/[\p{M}\p{Cf}]/gu, '').toLowerCase().trim().replace(/\s+/gu, ' ');
}

const jokeNames = new Set(policy.joke_names.map(normalize));
const substitutions: Record<string, string> = policy.substitutions;
const words = (text: string) => text.replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/).filter(Boolean);
const compact = (text: string) => words(text).join('');

// Repeated-character evasions are allowed only above the original run length:
// this catches n-ii-ggg-er without confusing a single-g ordinary name/place.
function repeatedPattern(term: string): RegExp {
  const runs = compact(term).match(/(.)\1*/g) ?? [];
  return new RegExp(`^${runs.map(run => `${run[0]}{${run.length},}`).join('')}$`);
}
const blockedPatterns = policy.blocked_terms.map(repeatedPattern);

/** Shared with api/name_policy.py; English filter, not an exhaustive multilingual moderation model. */
export function blockedPlayerNameReason(name: string): BlockedNameReason | null {
  const normalized = normalize(name);
  const withoutTrailingNumbers = normalized.replace(/[0-9]+(?=[^a-z0-9]|$)/g, '');
  const variants = [normalized, withoutTrailingNumbers].flatMap(value => [
    value, value.replace(/(^|[^a-z0-9])[0-9]+/g, '$1'),
  ]);
  const candidates: string[] = [];
  for (const variant of variants) {
    const decoded = [...variant].map(ch => substitutions[ch] ?? ch).join('');
    const tokens = words(decoded);
    candidates.push(...tokens, compact(decoded));
    // Join separated letters (e.g. "Mr f u c k") while preserving whole-word matching.
    let run = '';
    for (const token of [...tokens, '']) {
      if (token.length === 1) run += token;
      else { if (run) candidates.push(run); run = ''; }
    }
  }
  if (candidates.some(candidate => blockedPatterns.some(pattern => pattern.test(candidate)))) return 'language';
  return jokeNames.has(normalized) ? 'joke' : null;
}
