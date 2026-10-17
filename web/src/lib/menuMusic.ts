/**
 * Looping background music for the menu screens.
 *
 * The track is a LOCAL-ONLY asset: put it at web/public/audio/menu-bgm.mp3 on your own machine.
 * That folder is gitignored because the repo is public and must never contain audio (CLAUDE.md).
 * When the file is missing (a fresh clone, the public deployment) the player reports itself
 * unavailable and the app simply has no music.
 *
 * Browsers block audio until the user interacts with the page, so playback starts on the first
 * click or key press. The on/off choice is remembered per device.
 */
import { useSyncExternalStore } from 'react';

const SRC = '/audio/menu-bgm.mp3';
const VOLUME = 0.35;
const FADE_MS = 600;
const MUTE_KEY = 'just-sing.musicMuted';

export interface MenuMusicState {
  /** False until the file has loaded, and for good if it is missing. */
  available: boolean;
  muted: boolean;
}

let state: MenuMusicState = { available: false, muted: readMuted() };
let audio: HTMLAudioElement | null = null;
let wanted = false; // the current screen wants music
let unlocked = false; // the user has interacted, so play() is allowed
let fadeTimer: number | undefined;
const listeners = new Set<() => void>();

function readMuted(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === '1';
  } catch {
    return false;
  }
}

function setState(next: Partial<MenuMusicState>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

function element(): HTMLAudioElement {
  if (audio) return audio;
  audio = new Audio(SRC);
  audio.loop = true;
  audio.preload = 'auto';
  audio.volume = 0;
  audio.addEventListener('canplaythrough', () => setState({ available: true }), { once: true });
  audio.addEventListener('error', () => setState({ available: false }));
  return audio;
}

/** Ramp the volume to `target`, then pause if it reached zero. */
function fadeTo(target: number) {
  const a = element();
  window.clearInterval(fadeTimer);
  const steps = 12;
  const delta = (target - a.volume) / steps;
  let n = 0;
  fadeTimer = window.setInterval(() => {
    n += 1;
    a.volume = Math.min(1, Math.max(0, n >= steps ? target : a.volume + delta));
    if (n >= steps) {
      window.clearInterval(fadeTimer);
      if (target === 0) a.pause();
    }
  }, FADE_MS / steps);
}

/** Start or stop according to the screen, the mute switch, and the autoplay unlock. */
function sync() {
  const a = element();
  const shouldPlay = wanted && unlocked && !state.muted && state.available;
  if (shouldPlay) {
    if (a.paused) {
      a.volume = 0;
      a.play().then(() => fadeTo(VOLUME), () => undefined); // still blocked: retried on the next interaction
    } else {
      fadeTo(VOLUME);
    }
  } else if (!a.paused) {
    fadeTo(0);
  }
}

/** Call once at startup: preloads the track and unlocks playback on the first interaction. */
export function initMenuMusic() {
  element();
  listeners.add(sync); // availability or mute changes re-evaluate playback
  const unlock = () => {
    unlocked = true;
    sync();
  };
  window.addEventListener('pointerdown', unlock, { capture: true });
  window.addEventListener('keydown', unlock, { capture: true });
}

/** Whether the current screen should have music (off wherever the microphone is used). */
export function setMenuMusicWanted(on: boolean) {
  wanted = on;
  sync();
}

export function toggleMenuMusic() {
  const muted = !state.muted;
  try {
    localStorage.setItem(MUTE_KEY, muted ? '1' : '0');
  } catch {
    // storage blocked: the choice lasts for this session only
  }
  unlocked = true; // the toggle click itself counts as interaction
  setState({ muted });
}

export function useMenuMusic(): MenuMusicState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
  );
}
