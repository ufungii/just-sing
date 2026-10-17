/**
 * TypeScript mirrors of the shapes in contracts/ (and api/models.py).
 * Do not change these on your own: contracts change in their own PR, for the whole team.
 * Units: seconds from clip start; pitch in Hz (null = unvoiced); scores 0-100.
 */

export type Rating = 'perfect' | 'great' | 'okay' | 'bad' | 'miss';
export interface TimeRange { start: number; end: number }

export type Register = -12 | 0 | 12; // semitones, chosen before the turn

export interface ClipSummary {
  id: string;
  version: number;
  title: string;
  artist: string;
  duration: number;
  synthetic: boolean;
}

export interface Word {
  text: string;
  start: number;
  end: number;
}

export interface Line {
  start: number;
  end: number;
  text: string;
  romanized: string;
  translation: string;
  practice_text: string;
  words: Word[];
}

export interface Phrase {
  id: string;
  line_index: number;
  start: number;
  end: number;
}

export interface Note {
  start: number;
  end: number;
  hz: number;
}

export interface Excluded {
  start: number;
  end: number;
  reason: string;
}

export interface Song {
  id: string;
  version: number;
  title: string;
  artist: string;
  language: string;
  duration: number;
  provenance: { source_url: string | null; source_version: string; crop_start: number; crop_end: number };
  audio: { instrumental: string; vocals: string };
  lines: Line[];
  phrases: Phrase[];
  reference: { hop_seconds: number; hz: (number | null)[]; notes: Note[]; excluded: Excluded[] };
}

export interface PhraseScore {
  phrase_id: string;
  rating: Rating;
  pitch: number;
  timing: number | null; // null: the phrase starts mid-note, so it is scored on pitch alone
  score: number; // this phrase's 0-100 score (ratings and totals derive from it)
  coverage: number; // 0-1
}

export interface Score {
  range?: TimeRange | null;
  mode: 'solo' | 'battle';
  clip_id: string;
  clip_version: number;
  scoring_version: string;
  register: Register;
  total: number;
  pitch: number;
  timing: number;
  phrases: PhraseScore[];
  coach_blurb: string | null;
  guided?: boolean; // guide vocals were audible (client-reported); such runs skip the leaderboard
}

export interface WordFeedback {
  text: string;
  score: number;
}

export interface Practice {
  clip_id: string;
  phrase_id: string;
  locale: string;
  provider: string;
  status: 'ok' | 'unavailable' | 'error'; // 'unavailable' is not a score
  words: WordFeedback[];
}

export interface HistoryItem {
  range?: TimeRange | null;
  match_id: string;
  clip_id: string;
  created_at: string;
  total: number;
  guided?: boolean;
}

export interface MatchView {
  id: string;
  mode: 'solo' | 'local' | 'online';
  clip_id: string;
  state: string;
  active_slot: number;
  previous_match_id: string | null;
  players: { slot: number; display_name: string }[];
  winner_slot: number | null;
  attempts: { id: string; slot: number; state: string; score: Score | null }[];
}

export interface NewMatch {
  match_id: string;
  attempt_id: string;
  scoring_version: string;
}
