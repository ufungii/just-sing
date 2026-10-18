import { ApiError, checkTurnLyrics } from '../../lib/api';
import type { TurnLyrics } from '../../lib/types';

const uploads = new Map<string, Promise<TurnLyrics | null>>();

/** Continue across the transition to results. Local duets share one model with both online clients. */
export function uploadTurnLyrics(attemptId: string, take: { wav: Blob; offsetS: number }) {
  let upload = uploads.get(attemptId);
  if (!upload) {
    upload = (async () => {
      const deadline = performance.now() + 180_000;
      while (true) {
        try { return await checkTurnLyrics(attemptId, take.wav, take.offsetS); }
        catch (e) {
          if (!(e instanceof ApiError && (e.code === 'pronunciation_busy' || e.code === 'network')) || performance.now() >= deadline) return null;
          await new Promise((resolve) => setTimeout(resolve, 4000));
        }
      }
    })();
    uploads.set(attemptId, upload);
    // Only an in-flight promise is needed; the server caches successful feedback.
    void upload.finally(() => uploads.delete(attemptId));
  }
  return upload;
}
