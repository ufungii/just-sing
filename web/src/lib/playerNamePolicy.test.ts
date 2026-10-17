import { describe, expect, it } from 'vitest';
import cases from '../../../contracts/fixtures/player_names.json';
import policy from '../../../contracts/player-name-policy.json';
import { blockedPlayerNameReason } from './playerNamePolicy';

describe('shared player-name policy', () => {
  it.each(cases.cases)('classifies $name', ({ name, reason }) => {
    expect(blockedPlayerNameReason(name)).toBe(reason);
  });
  it('blocks every configured profanity/slur term', () => {
    for (const term of policy.blocked_terms) expect(blockedPlayerNameReason(term), term).toBe('language');
  });
});
