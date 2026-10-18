/**
 * The live lyric check: while the song plays, each lyric line is sent to the server as soon as it has
 * been sung, so the results are ready when the song ends (checking the whole take afterwards takes
 * about 10 s per 35 s of singing on the server's CPU). One request at a time, in line order; it never
 * blocks the game. Display only on this side: the server decides the statuses.
 */
import { ApiError, checkLyricLine } from '../../lib/api';
import type { Line, LyricStatus } from '../../lib/types';
import type { TakeRecorder } from '../../audio/takeRecorder';

/** Audio kept around each line: a little before its start, and after its end for held notes. */
export const LINE_PRE_S = 0.3;
export const LINE_POST_S = 0.5;
/** Extra wait after a line ends before its audio is surely captured (worklet batches, device latency). */
const CAPTURE_SLACK_S = 0.4;

export class LiveLyricChecker {
  readonly results = new Map<number, LyricStatus>();
  /** Lines whose audio has been sent (their answer may still be on the way). */
  readonly sent = new Set<number>();
  private readonly pending: { index: number; line: Line }[];
  private chain: Promise<void> = Promise.resolve();
  private stopped = false; // the server said "unavailable", or a request failed outright
  private failed = false;

  constructor(
    private readonly clipId: string,
    lines: { index: number; line: Line }[],
    private readonly recorder: TakeRecorder,
    /** Called whenever a line's status arrives (for the live chip and lyric highlights). */
    private readonly onResult: () => void = () => {},
    /** Called when a line's audio is sent, so the lyrics can show "checking…". */
    private readonly onSent: (index: number) => void = () => {},
  ) {
    this.pending = [...lines].sort((a, b) => a.line.end - b.line.end);
  }

  /** Call every frame with the clip time; sends each line once its audio has been captured. */
  poll(t: number) {
    while (!this.stopped && this.pending.length && t >= this.pending[0].line.end + LINE_POST_S + CAPTURE_SLACK_S) {
      const { index, line } = this.pending.shift()!;
      const { wav, offsetS } = this.recorder.slice(line.start - LINE_PRE_S, line.end + LINE_POST_S);
      this.sent.add(index);
      this.onSent(index);
      this.chain = this.chain.then(() => this.send(index, wav, offsetS));
    }
  }

  private async send(index: number, wav: Blob, offsetS: number) {
    if (this.stopped) return;
    try {
      const r = await checkLyricLine(this.clipId, index, wav, offsetS).catch(async (e) => {
        if (!(e instanceof ApiError && e.code === 'pronunciation_busy')) throw e;
        await new Promise((resolve) => setTimeout(resolve, 2000)); // shared model busy: one retry
        return checkLyricLine(this.clipId, index, wav, offsetS);
      });
      if (r.status === 'unavailable') return void (this.stopped = true); // no checker or fingerprints: stop sending
      for (const l of r.lines) this.results.set(l.line_index, l.status);
      if (r.status === 'error') this.failed = true;
      this.onResult();
    } catch {
      this.failed = true; // a lost line: the results screen falls back to checking the whole take
    }
  }

  /**
   * After the song: send any lines not yet sent, wait for all answers (up to `timeoutMs`), and return
   * the statuses, or null if the live check was unavailable or incomplete (then check the whole take).
   */
  async finish(timeoutMs = 15_000): Promise<Map<number, LyricStatus> | null> {
    this.poll(Number.POSITIVE_INFINITY);
    const done = await Promise.race([this.chain.then(() => true), new Promise<boolean>((r) => setTimeout(() => r(false), timeoutMs))]);
    if (!done || this.stopped || this.failed) return null;
    return new Map(this.results);
  }
}
