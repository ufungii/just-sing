/**
 * Spoken Korean pronunciation practice ("SAY IT RIGHT").
 * The player picks one lyric phrase, reads it aloud at speaking pace (not sung: ASR on singing is
 * unreliable), and gets word-level feedback from the server's local pronunciation scorer.
 * This mode never touches the singing score. An offline scorer is a state with retry, never a low score.
 */
import { useEffect, useRef, useState } from 'react';
import { ApiError, asGuest, getClips, getManifest, savedName, submitPractice } from '../../lib/api';
import type { ClipSummary, Practice as PracticeResult, Song } from '../../lib/types';
import { Notice, Panel, PixelButton, ScreenShell, Segmented } from '../../ui';
import { Recorder } from './Recorder';
import './Practice.css';

/**
 * Display-only bands for colouring word chips. These are NOT validated thresholds: the scorer's
 * 0-100 scale has not been calibrated against a fluent reviewer, so they only group the numbers.
 */
const WORD_BANDS = [
  { min: 80, label: 'Nice!', kao: '☆', tone: 'good' },
  { min: 55, label: 'Almost', kao: '(^_^)', tone: 'mid' },
  { min: 0, label: 'Try again', kao: '(・_・;)', tone: 'low' },
] as const;

const bandFor = (score: number) => WORD_BANDS.find((b) => score >= b.min) ?? WORD_BANDS[WORD_BANDS.length - 1];

type Check =
  | { state: 'idle' }
  | { state: 'checking' }
  | { state: 'done'; result: PracticeResult }
  | { state: 'failed'; message: string; retry: boolean };

/** Turns an upload failure into something a player can act on. */
function describeError(e: unknown): { message: string; retry: boolean } {
  if (!(e instanceof ApiError)) return { message: 'Something went wrong while checking your take.', retry: true };
  switch (e.code) {
    case 'pronunciation_busy':
      return { message: 'The checker is busy with someone else. Try again in a few seconds.', retry: true };
    case 'audio_too_long':
      return { message: 'That take is longer than 15 seconds. Re-record just this line, a little quicker.', retry: false };
    case 'audio_too_large':
      return { message: 'That recording is too big to upload. Re-record a shorter take.', retry: false };
    case 'unsupported_audio':
      return { message: "The server couldn't read that recording. Re-record and try again.", retry: false };
    case 'network':
      return { message: "Can't reach the server. Check the connection and try again.", retry: true };
    case 'phrase_not_found':
      return { message: 'The server does not know this line any more. Pick the line again.', retry: false };
    default:
      if (e.status >= 500 || e.code.startsWith('http_')) {
        return { message: 'The server hit a problem checking your take. Give it a moment and try again.', retry: true };
      }
      return { message: `Couldn't check your take: ${e.message}`, retry: e.retryable };
  }
}

export function Practice() {
  const [clips, setClips] = useState<ClipSummary[] | null>(null);
  const [clipsError, setClipsError] = useState<string | null>(null);
  const [clipsTry, setClipsTry] = useState(0);
  const [clipId, setClipId] = useState<string | null>(null);

  const [song, setSong] = useState<Song | null>(null);
  const [songError, setSongError] = useState<string | null>(null);
  const [songTry, setSongTry] = useState(0);
  const [phraseId, setPhraseId] = useState<string | null>(null);

  const [showRoman, setShowRoman] = useState(true);
  const [showTrans, setShowTrans] = useState(true);

  const [take, setTake] = useState<Blob | null>(null);
  const takeRef = useRef<Blob | null>(null); // the latest take, to drop answers for replaced ones
  const replaceTake = (blob: Blob | null) => {
    takeRef.current = blob;
    setTake(blob);
    setCheck({ state: 'idle' });
  };
  const [check, setCheck] = useState<Check>({ state: 'idle' });

  // Load the catalog.
  useEffect(() => {
    let live = true;
    setClipsError(null);
    getClips()
      .then((list) => {
        if (!live) return;
        setClips(list);
        setClipId((cur) => cur ?? list[0]?.id ?? null);
      })
      .catch((e) => live && setClipsError(e instanceof ApiError ? e.message : 'Could not load clips.'));
    return () => {
      live = false;
    };
  }, [clipsTry]);

  // Load the chosen clip's manifest for its phrases.
  useEffect(() => {
    if (!clipId) return;
    let live = true;
    setSong(null);
    setSongError(null);
    getManifest(clipId)
      .then((s) => {
        if (!live) return;
        setSong(s);
        setPhraseId(s.phrases[0]?.id ?? null);
      })
      .catch((e) => live && setSongError(e instanceof ApiError ? e.message : 'Could not load this clip.'));
    return () => {
      live = false;
    };
  }, [clipId, songTry]);

  // A new line means a new take and fresh feedback.
  useEffect(() => replaceTake(null), [clipId, phraseId]);

  const phrase = song?.phrases.find((p) => p.id === phraseId) ?? null;
  const line = phrase && song ? song.lines[phrase.line_index] : null;

  async function runCheck() {
    if (!take || !clipId || !phraseId) return;
    const forTake = take;
    setCheck({ state: 'checking' });
    try {
      const result = await asGuest(savedName() || 'Player', () => submitPractice(clipId, phraseId, forTake));
      if (takeRef.current === forTake) setCheck({ state: 'done', result }); // ignore answers for a replaced take
    } catch (e) {
      if (takeRef.current === forTake) setCheck({ state: 'failed', ...describeError(e) });
    }
  }

  return (
    <ScreenShell title="SAY IT RIGHT" kao="˚｡♪">
      <p className="practice-intro">
        Read one lyric line <strong>out loud at normal speaking pace</strong> (no singing!) and see which words came through.
      </p>

      {clipsError && (
        <Notice tone="error" action={<PixelButton tone="paper" size="sm" onClick={() => setClipsTry((n) => n + 1)}>RETRY</PixelButton>}>
          {clipsError}
        </Notice>
      )}
      {!clips && !clipsError && <Notice>Loading clips…</Notice>}
      {clips && clips.length === 0 && <Notice tone="warn">No clips are installed on this server yet.</Notice>}

      {clips && clips.length > 0 && (
        <div className="practice-grid">
          {/* ---------- left: choose a line ---------- */}
          <Panel label="1 · PICK A LINE" className="practice-pick">
            {clips.length > 1 && (
              <div className="practice-field">
                <span className="practice-field__label">CLIP</span>
                <Segmented
                  label="Clip"
                  tone="mint"
                  value={clipId ?? ''}
                  onChange={setClipId}
                  options={clips.map((c) => ({ value: c.id, label: c.title }))}
                />
              </div>
            )}
            {clips.length === 1 && (
              <p className="practice-clipname">
                {clips[0].title} <span>· {clips[0].artist}</span>
              </p>
            )}

            {songError && (
              <Notice tone="error" action={<PixelButton tone="paper" size="sm" onClick={() => setSongTry((n) => n + 1)}>RETRY</PixelButton>}>
                {songError}
              </Notice>
            )}
            {!song && !songError && <Notice>Loading lines…</Notice>}
            {song && (
              <ol className="practice-lines">
                {song.phrases.map((p, i) => {
                  const l = song.lines[p.line_index];
                  return (
                    <li key={p.id}>
                      <button
                        type="button"
                        className="practice-line"
                        aria-pressed={p.id === phraseId}
                        onClick={() => setPhraseId(p.id)}
                      >
                        <span className="practice-line__n">{String(i + 1).padStart(2, '0')}</span>
                        <span className="practice-line__ko" lang="ko">{l?.practice_text}</span>
                        <span className="practice-line__ro">{l?.romanized}</span>
                      </button>
                    </li>
                  );
                })}
              </ol>
            )}
          </Panel>

          {/* ---------- right: say it ---------- */}
          <div className="practice-main">
            <Panel tone="mint" label="2 · SAY THIS" className="practice-card">
              {line ? (
                <>
                  <p className="practice-ko" lang="ko">{line.practice_text}</p>
                  {showRoman && <p className="practice-roman">{line.romanized}</p>}
                  {showTrans && <p className="practice-trans">“{line.translation}”</p>}
                  <div className="practice-toggles">
                    <PixelButton tone="paper" size="sm" aria-pressed={showRoman} onClick={() => setShowRoman((v) => !v)}>
                      ROMANIZATION
                    </PixelButton>
                    <PixelButton tone="paper" size="sm" aria-pressed={showTrans} onClick={() => setShowTrans((v) => !v)}>
                      TRANSLATION
                    </PixelButton>
                  </div>
                </>
              ) : (
                <p className="practice-muted">Pick a line on the left.</p>
              )}
            </Panel>

            <Panel label="3 · RECORD" className="practice-rec-panel">
              {/* Keyed on the line so switching lines drops the old recorder (and its mic) cleanly. */}
              <Recorder key={`${clipId}/${phraseId}`} disabled={!line} onTake={replaceTake} />
            </Panel>

            <Panel label="4 · CHECK IT" className="practice-check">
              <div className="practice-check__row">
                <PixelButton
                  tone="hot"
                  size="lg"
                  disabled={!take || check.state === 'checking'}
                  onClick={runCheck}
                >
                  {check.state === 'checking' ? 'CHECKING…' : 'CHECK IT ▶'}
                </PixelButton>
                {!take && <span className="practice-muted">Record a take first.</span>}
              </div>
              <Feedback check={check} onRetry={runCheck} />
              <p className="practice-disclaimer">
                Automated word-level feedback. Not reviewed by a fluent speaker. Doesn't affect singing scores.
              </p>
            </Panel>
          </div>
        </div>
      )}
    </ScreenShell>
  );
}

function Feedback({ check, onRetry }: { check: Check; onRetry: () => void }) {
  const retry = (
    <PixelButton tone="paper" size="sm" onClick={onRetry}>
      RETRY
    </PixelButton>
  );
  if (check.state === 'idle' || check.state === 'checking') return null;
  if (check.state === 'failed') {
    return (
      <Notice tone={check.retry ? 'warn' : 'error'} action={check.retry ? retry : undefined}>
        {check.message}
      </Notice>
    );
  }
  const { result } = check;
  if (result.status === 'unavailable') {
    return (
      <Notice tone="warn" action={retry}>
        Pronunciation feedback is offline right now — this is not a score.
      </Notice>
    );
  }
  if (result.status === 'error' || result.words.length === 0) {
    return (
      <Notice tone="error" action={retry}>
        The checker hit a snag on this take. That's on us, not you — try again.
      </Notice>
    );
  }
  return (
    <ul className="practice-words" aria-label="Word feedback">
      {result.words.map((w, i) => {
        const band = bandFor(w.score);
        return (
          <li key={i} className={`practice-word practice-word--${band.tone}`}>
            <span className="practice-word__ko" lang="ko">{w.text}</span>
            <span className="practice-word__label">
              <span className="practice-kao" aria-hidden="true">{band.kao}</span> {band.label}
            </span>
            <span className="practice-word__score">{Math.round(w.score)}</span>
          </li>
        );
      })}
    </ul>
  );
}
