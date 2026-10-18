/**
 * Song-select preview: while a song is chosen on the wheel, play a short loop of it, the way an
 * arcade cabinet does. It plays the song's original recording (original.mp3 on the server). A song
 * without one falls back to the vocals and instrumental stems played together, which sounds less
 * natural. All audio is local-only on the server (never in the repo), so a server without it stays quiet.
 *
 * The menu-music on/off switch also mutes previews, so one switch silences the menus.
 */
import { useEffect } from 'react';
import { audioUrl, previewUrl, vocalsUrl } from '../../lib/api';
import { useMenuMusic } from '../../lib/menuMusic';

const VOLUME = 0.45;
const LOOP_SECONDS = 30;
const FADE_MS = 500;
/** Wait a moment before loading, so scrolling through the wheel doesn't fetch every song. */
const SETTLE_MS = 250;

/** Where the loop starts: past the intro, but leaving a full loop before the end of the audio. */
function previewStart(duration: number): number {
  return Math.max(0, Math.min(duration * 0.3, 45, duration - LOOP_SECONDS));
}

export function useSongPreview(clipId: string | null, duration: number | null) {
  const { muted } = useMenuMusic();

  useEffect(() => {
    if (!clipId || duration === null || muted) return;
    // The original recording if the server has it, else the two stems (switched to on a load error).
    let players = [new Audio()];
    let start = previewStart(duration);
    let end = Math.min(duration, start + LOOP_SECONDS);
    let fade: number | undefined;
    let stopped = false;

    // Ramp both stems from their current volume to `target` over FADE_MS.
    const fadeTo = (target: number, then?: () => void) => {
      window.clearInterval(fade);
      const from = players[0].volume;
      let n = 0;
      fade = window.setInterval(() => {
        n += 1;
        const v = from + ((target - from) * n) / 10;
        players.forEach((a) => (a.volume = Math.min(1, Math.max(0, v))));
        if (n >= 10) {
          window.clearInterval(fade);
          then?.();
        }
      }, FADE_MS / 10);
    };

    const playFromStart = () => {
      if (stopped) return;
      players.forEach((a) => {
        a.currentTime = start;
        a.volume = 0;
      });
      // Autoplay may still be blocked before the first click; then the preview just stays silent.
      Promise.allSettled(players.map((a) => a.play())).then((r) => {
        if (!stopped && r.some((p) => p.status === 'fulfilled')) fadeTo(VOLUME);
      });
    };

    // Fade out near the end of the window, then jump back to the start (the first player leads).
    const onTime = () => {
      if (players[0].currentTime >= end - FADE_MS / 1000 && players[0].volume >= VOLUME - 0.01) fadeTo(0, playFromStart);
    };

    // The original's own length decides the window: it can differ from the prepared clip's.
    const fitWindow = (a: HTMLAudioElement) => {
      const length = Number.isFinite(a.duration) ? a.duration : duration;
      start = previewStart(length);
      end = Math.min(length, start + LOOP_SECONDS);
      a.currentTime = start;
    };

    // No original on this server: mix the instrumental and vocals stems instead.
    const useStems = () => {
      if (stopped || players.length > 1) return;
      window.clearInterval(fade);
      players[0].pause();
      players[0].removeAttribute('src');
      players[0].load();
      players = [new Audio(), new Audio()];
      players[0].src = audioUrl(clipId);
      players[1].src = vocalsUrl(clipId);
      players.forEach((a) => (a.preload = 'auto'));
      players[0].addEventListener('timeupdate', onTime);
      // A missing stem (e.g. a test clip with no vocals) is fine: the other one still plays.
      players[1].addEventListener('error', () => players[1].pause());
      start = previewStart(duration);
      end = Math.min(duration, start + LOOP_SECONDS);
      playFromStart();
    };

    const settle = window.setTimeout(() => {
      const [original] = players;
      original.src = previewUrl(clipId);
      original.preload = 'auto';
      original.addEventListener('timeupdate', onTime);
      original.addEventListener('error', useStems);
      original.addEventListener('loadedmetadata', () => fitWindow(original), { once: true });
      playFromStart();
    }, SETTLE_MS);

    return () => {
      stopped = true;
      window.clearTimeout(settle);
      window.clearInterval(fade);
      players.forEach((a) => {
        a.pause();
        a.removeAttribute('src');
        a.load(); // drop the download
      });
    };
  }, [clipId, duration, muted]);
}
