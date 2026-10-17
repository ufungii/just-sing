/** Live scoring: TypeScript port of ml/scoring (see score.ts). */
export { SCORING_CONFIG, SCORING_VERSION } from './config';
export { buildTargetTrack, displayNotes, registerRatio, type TargetTrack } from './reference';
export { aggregate, phraseSettlesAt, phraseTotal, phraseWeights, scorePhrase } from './score';
export { centsBetween } from './units';
