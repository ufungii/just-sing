import { useEffect, useState } from 'react';
import { asGuest, getMatch, rematch } from '../../lib/api';
import type { MatchView } from '../../lib/types';
import { useNav, type BattleCtx, type SingResult, type SingSetup } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell } from '../../ui';
import { PhraseChips, ScoreSummary } from '../Results/PhraseChips';
import { useManifest } from '../Results/useManifest';
import { buildTargetTrack, phraseWeights, pronunciationScore } from '../../scoring';
import './MatchBoard.css';
import { shortName } from '../../lib/players';

/** The battle screen after a turn: the hand-off after player 1, the final results after player 2. */
export function BattleTurn({ result }: { result: SingResult }) {
  const battle = result.setup.battle as BattleCtx;
  return battle.turn === 0 ? <HandOff result={result} battle={battle} /> : <BattleResults result={result} battle={battle} />;
}

/** "Pass the headphones": fetches player 2's attempt from the server, then opens their turn. */
function HandOff({ result, battle }: { result: SingResult; battle: BattleCtx }) {
  const nav = useNav();
  const { setup, saved } = result;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function next() {
    if (!setup.match) return;
    const matchId = setup.match.matchId;
    setBusy(true);
    setError(null);
    try {
      const m = await asGuest(setup.playerName, () => getMatch(matchId));
      const attempt = m.attempts.find((a) => a.slot === 1);
      if (!attempt) throw new Error('Player 2’s turn is not open yet.');
      nav.go({
        name: 'sing',
        setup: {
          runId: crypto.randomUUID(),
          clipId: setup.clipId,
          register: battle.registers[1],
          calibrationOffset: battle.calibrationOffset,
          playerName: battle.names[1],
          match: { matchId, attemptId: attempt.id },
          battle: { ...battle, turn: 1 },
        },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <ScreenShell title="PASS THE MIC" kao="(^o^)ﾉ ⇄ ヽ(^o^)">
      <Panel tone="sky" label={`${battle.names[0].toUpperCase()} IS DONE`}>
        {saved ? (
          <p style={{ fontSize: 22, margin: '0 0 16px' }}>
            Pass the headphones to <strong>{battle.names[1]}</strong>. The score stays hidden until both have sung.
          </p>
        ) : (
          <Notice tone="error">
            {battle.names[0]}’s score was not saved ({result.saveError ?? 'unknown error'}), so the battle can’t continue. Start a new
            battle once the server is back.
          </Notice>
        )}
        {error && <Notice tone="error">{error}</Notice>}
        <div className="results-actions">
          {saved ? (
            <PixelButton tone="hot" size="lg" disabled={busy} onClick={next}>
              {busy ? 'LOADING…' : `${battle.names[1].toUpperCase()}: READY ▶`}
            </PixelButton>
          ) : (
            <PixelButton tone="hot" size="lg" onClick={() => nav.go({ name: 'battle' })}>
              BACK TO SETUP
            </PixelButton>
          )}
        </div>
      </Panel>
    </ScreenShell>
  );
}

/** Both totals and the winner, read from the server's saved match (the client only displays it). */
function BattleResults({ result, battle }: { result: SingResult; battle: BattleCtx }) {
  const nav = useNav();
  const { setup } = result;
  const matchId = setup.match?.matchId;
  const song = useManifest(setup.clipId);
  const [match, setMatch] = useState<MatchView | null>(null);
  const [error, setError] = useState<string | null>(result.saved ? null : result.saveError ?? 'not saved');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!matchId || !result.saved) return;
    let live = true;
    asGuest(setup.playerName, () => getMatch(matchId)).then(
      (m) => live && setMatch(m),
      (e: Error) => live && setError(e.message),
    );
    return () => {
      live = false;
    };
  }, [matchId, result.saved, setup.playerName]);

  async function again() {
    if (!matchId) return;
    setBusy(true);
    try {
      const m = await asGuest(setup.playerName, () => rematch(matchId));
      const next: SingSetup = {
        runId: crypto.randomUUID(),
        clipId: setup.clipId,
        register: battle.registers[0],
        calibrationOffset: battle.calibrationOffset,
        playerName: battle.names[0],
        match: { matchId: m.match_id, attemptId: m.attempt_id },
        battle: { ...battle, turn: 0 },
      };
      nav.go({ name: 'sing', setup: next });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <ScreenShell title="BATTLE RESULTS" kao="ヾ(＾∇＾)">
      {error && <Notice tone="error">Couldn’t load the battle result: {error}</Notice>}
      {!match && !error && <Notice>Counting the votes…</Notice>}
      {match && <MatchBoard match={match} song={song} />}
      <div className="results-actions">
        <PixelButton tone="hot" size="lg" onClick={again} disabled={busy || !matchId}>
          {busy ? 'STARTING…' : '↻ REMATCH'}
        </PixelButton>
        <PixelButton tone="sky" size="lg" onClick={() => nav.go({ name: 'battle' })}>
          ♪ NEW SETUP
        </PixelButton>
        <PixelButton tone="mint" size="lg" onClick={nav.home}>
          HOME
        </PixelButton>
      </div>
    </ScreenShell>
  );
}

/** Winner headline plus both players' saved scores, read from the server's match (the client only displays it). Shared with online rooms. */
export function MatchBoard({ match, song }: { match: MatchView; song: ReturnType<typeof useManifest> }) {
  const [updated, setUpdated] = useState(match);
  useEffect(() => { setUpdated(match); }, [match]);
  const view = updated.id === match.id ? updated : match;
  const checking = view.attempts.some((a) => a.score?.lyrics?.status === 'pending');
  useEffect(() => {
    if (!checking) return;
    let live = true;
    let busy = false;
    const timer = setInterval(async () => {
      if (busy) return;
      busy = true;
      try { const next = await getMatch(match.id); if (live) setUpdated(next); }
      catch { /* A later poll recovers; the server expires missing uploads after three minutes. */ }
      finally { busy = false; }
    }, 2000);
    return () => { live = false; clearInterval(timer); };
  }, [match.id, checking]);
  const headline =
    view.state !== 'finished'
      ? 'Waiting for the final score…'
      : view.winner_slot === null
        ? 'TIE!'
        : `${shortName(view.players.find((p) => p.slot === view.winner_slot)?.display_name ?? '?')} WINS!`;
  return (
    <>
      <Panel tone="mint" label="WINNER">
        <p className="battle-headline" style={{ fontSize: 40, margin: 0 }} aria-live="polite">{headline}</p>
      </Panel>
      <div className="match-board__players">
      {view.players.map((p) => {
        const score = view.attempts.find((a) => a.slot === p.slot && a.state === 'accepted')?.score;
        const feedback = score?.lyrics;
        const lines = feedback?.status === 'ok' ? new Map(feedback.lines.map((l) => [l.line_index, l.status])) : undefined;
        const graded = [...(lines?.values() ?? [])].filter((s) => s === 'match' || s === 'unclear');
        let pronunciation: number | null = null;
        if (song && score && lines) {
          const ids = new Set(score.phrases.map((p) => p.phrase_id));
          const phrases = song.phrases.filter((p) => ids.has(p.id));
          const weights = phraseWeights(phrases, buildTargetTrack(song, score.register));
          const byLine = new Map<number, number>();
          for (const p of phrases) byLine.set(p.line_index, (byLine.get(p.line_index) ?? 0) + (weights.get(p.id) ?? 0));
          pronunciation = pronunciationScore(lines, byLine);
        }
        const lyrics = feedback?.status === 'pending' ? 'checking' as const : lines
          ? { matched: graded.filter((s) => s === 'match').length, graded: graded.length, score: pronunciation } : 'unavailable' as const;
        return (
          <Panel key={p.slot} className={view.state === 'finished' && view.winner_slot === p.slot ? 'match-board__winner' : undefined} tone={p.slot === 0 ? 'pink' : 'sky'} label={`P${p.slot + 1} · ${shortName(p.display_name).toUpperCase()}`}>
            {score ? (
              <>
                <ScoreSummary total={score.total} pitch={score.pitch} timing={score.timing} range={score.range} lyrics={lyrics} decimals />
                <PhraseChips phrases={score.phrases} song={song} lyrics={lines} />
              </>
            ) : (
              <Notice tone="warn">No saved score for this player.</Notice>
            )}
          </Panel>
        );
      })}
      </div>
    </>
  );
}
