/** Live scoring (provisional TypeScript port of the CLAUDE.md spec; see score.ts). */
export { SCORING_CONFIG, SCORING_VERSION } from './config';
export { buildTargetTrack, displayNotes, registerRatio, targetOnsets, type TargetTrack } from './reference';
export { aggregate, phraseSettlesAt, phraseTotal, scorePhrase } from './score';
export { centsBetween } from './units';
