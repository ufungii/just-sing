/**
 * Mic-chan's coaching blurb for one saved turn. Gemini only writes words about the measured numbers;
 * it never produces a score or a winner. Shared by the solo results and the online 1v1 results.
 */
import { useEffect, useState } from 'react';
import { MicChan } from '../../components/pixel';
import { getCoach } from '../../lib/api';
import { Panel } from '../../ui';
import './Results.css';

type Coach =
  | { state: 'none' } // turn not saved, so there is nothing to coach on the server
  | { state: 'loading' }
  | { state: 'ok'; text: string }
  | { state: 'offline' }; // Gemini unavailable or the call failed: not an error, just no blurb

export function useCoach(attemptId: string | null): Coach {
  const [coach, setCoach] = useState<Coach>(attemptId ? { state: 'loading' } : { state: 'none' });
  useEffect(() => {
    if (!attemptId) return;
    let live = true;
    getCoach(attemptId).then(
      (r) => live && setCoach(r.status === 'ok' && r.coach_blurb ? { state: 'ok', text: r.coach_blurb } : { state: 'offline' }),
      () => live && setCoach({ state: 'offline' }),
    );
    return () => {
      live = false;
    };
  }, [attemptId]);
  return coach;
}

/** `attemptId` null means the turn was not saved, so there is nothing to coach on the server. */
export function CoachPanel({ attemptId }: { attemptId: string | null }) {
  const coach = useCoach(attemptId);
  return (
    <Panel tone="lav" label="COACH" className="results-coach">
      <div className="results-coach__row">
        <MicChan className="results-coach__mascot" />
        <p className="results-bubble" aria-live="polite">
          {coach.state === 'ok' && coach.text}
          {coach.state === 'loading' && <span className="results-bubble__wait">thinking (・_・;) …</span>}
          {coach.state === 'offline' && <>coach is offline right now ♪ your scores are all here, though!</>}
          {coach.state === 'none' && <>save a turn and I'll leave you a tip ♡</>}
        </p>
      </div>
      {coach.state === 'ok' && <p className="results-fine">Written by Gemini from your measured scores only.</p>}
    </Panel>
  );
}
