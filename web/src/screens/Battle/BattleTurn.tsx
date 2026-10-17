import { useEffect, useState } from 'react';
import { asGuest, getMatch, rematch } from '../../lib/api';
import type { MatchView } from '../../lib/types';
import { useNav, type BattleCtx, type SingResult, type SingSetup } from '../../routes';
import { Notice, Panel, PixelButton, ScreenShell } from '../../ui';
import { PhraseChips, ScoreSummary } from '../Results/PhraseChips';
import { useManifest } from '../Results/useManifest';

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

  const finished = match?.state === 'finished';
  const headline = !match
    ? ''
    : !finished
      ? 'Waiting for the final score…'
      : match.winner_slot === null
        ? 'TIE!'
        : `${match.players.find((p) => p.slot === match.winner_slot)?.display_name ?? '?'} WINS!`;

  return (
    <ScreenShell title="BATTLE RESULTS" kao="ヾ(＾∇＾)">
      {error && <Notice tone="error">Couldn’t load the battle result: {error}</Notice>}
      {!match && !error && <Notice>Counting the votes…</Notice>}
      {match && (
        <>
          <Panel tone="mint" label="WINNER">
            <p className="battle-headline" style={{ fontSize: 40, margin: 0 }} aria-live="polite">{headline}</p>
          </Panel>
          {match.players.map((p) => {
            const score = match.attempts.find((a) => a.slot === p.slot && a.state === 'accepted')?.score;
            return (
              <Panel key={p.slot} tone={p.slot === 0 ? 'pink' : 'sky'} label={`P${p.slot + 1} · ${p.display_name.toUpperCase()}`}>
                {score ? (
                  <>
                    <ScoreSummary total={score.total} pitch={score.pitch} timing={score.timing} />
                    <PhraseChips phrases={score.phrases} song={song} />
                  </>
                ) : (
                  <Notice tone="warn">No saved score for this player.</Notice>
                )}
              </Panel>
            );
          })}
        </>
      )}
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
