import { toggleMenuMusic, useMenuMusic } from '../lib/menuMusic';
import { PixelButton } from './index';

/** Small keycap in the bottom-right corner that turns the menu music on or off. Hidden when there is no track. */
export function MusicToggle() {
  const { available, muted } = useMenuMusic();
  if (!available) return null;
  return (
    <PixelButton
      tone={muted ? 'paper' : 'butter'}
      size="sm"
      className="ui-music-toggle"
      aria-pressed={!muted}
      aria-label={muted ? 'Turn menu music on' : 'Turn menu music off'}
      onClick={toggleMenuMusic}
    >
      {muted ? '♪ OFF' : '♪ ON'}
    </PixelButton>
  );
}
