/**
 * Song-select preview: while a song is chosen on the wheel, play a short loop of it, the way an
 * arcade cabinet does. The vocals and instrumental stems are played together so the preview sounds
 * like the real song. Both come from the prepared clip on the server (local-only audio, never in
 * the repo), so a server without the audio just stays quiet.
 *
 * The menu-music on/off switch also mutes previews, so one switch silences the menus.
 */
import { useEffect } from 'react';
import { audioUrl, vocalsUrl } from '../../lib/api';
import { useMenuMusic } from '../../lib/menuMusic';

const VOLUME = 0.45;
const LOOP_SECONDS = 30;
const FADE_MS = 500;
/** Wait a moment before loading, so scrolling through the wheel doesn't fetch every song. */
const SETTLE_MS = 250;

/** Where the loop starts: past the intro, but leaving a full loop before the end of the clip. */
function previewStart(duration: number): number {
  return Math.max(0, Math.min(duration * 0.3, 45, duration - LOOP_SECONDS));
}

export function useSongPreview(clipId: string | null, duration: number | null) {
  const { muted } = useMenuMusic();

  useEffect(() => {
    if (!clipId || duration === null || muted) return;
    const stems = [new Audio(), new Audio()];
    const start = previewStart(duration);
    const end = Math.min(duration, start + LOOP_SECONDS);
    let fade: number | undefined;
    let stopped = false;

    // Ramp both stems from their current volume to `target` over FADE_MS.
    const fadeTo = (target: number, then?: () => void) => {
      window.clearInterval(fade);
      const from = stems[0].volume;
      let n = 0;
      fade = window.setInterval(() => {
        n += 1;
        const v = from + ((target - from) * n) / 10;
        stems.forEach((a) => (a.volume = Math.min(1, Math.max(0, v))));
        if (n >= 10) {
          window.clearInterval(fade);
          then?.();
        }
      }, FADE_MS / 10);
    };

    const playFromStart = () => {
      if (stopped) return;
      stems.forEach((a) => {
        a.currentTime = start;
        a.volume = 0;
      });
      // Autoplay may still be blocked before the first click; then the preview just stays silent.
      Promise.allSettled(stems.map((a) => a.play())).then((r) => {
        if (!stopped && r.some((p) => p.status === 'fulfilled')) fadeTo(VOLUME);
      });
    };

    // Fade out near the end of the window, then jump back to the start (the instrumental leads).
    const onTime = () => {
      if (stems[0].currentTime >= end - FADE_MS / 1000 && stems[0].volume >= VOLUME - 0.01) fadeTo(0, playFromStart);
    };

    const settle = window.setTimeout(() => {
      stems[0].src = audioUrl(clipId);
      stems[1].src = vocalsUrl(clipId);
      stems.forEach((a) => (a.preload = 'auto'));
      stems[0].addEventListener('timeupdate', onTime);
      // A missing stem (e.g. a test clip with no vocals) is fine: the other one still plays.
      stems[1].addEventListener('error', () => stems[1].pause());
      playFromStart();
    }, SETTLE_MS);

    return () => {
      stopped = true;
      window.clearTimeout(settle);
      window.clearInterval(fade);
      stems.forEach((a) => {
        a.pause();
        a.removeAttribute('src');
        a.load(); // drop the download
      });
    };
  }, [clipId, duration, muted]);
}
