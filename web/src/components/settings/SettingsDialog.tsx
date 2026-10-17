import { useEffect, useState } from 'react';
import { toggleMenuMusic, useMenuMusic } from '../../lib/menuMusic';
import { CALIBRATION_KEY, loadCalibration } from '../../screens/Solo/TimingCheck';
import { Notice, PixelButton } from '../../ui';
import { Dialog } from '../../ui/Dialog';
import './settings.css';

/** App settings: menu music on/off and the saved timing calibration for this device. */
export function SettingsDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const music = useMenuMusic();
  const [offset, setOffset] = useState<number | null>(loadCalibration);
  useEffect(() => {
    if (open) setOffset(loadCalibration()); // it may have been measured since the last visit
  }, [open]);

  function resetTiming() {
    try {
      localStorage.removeItem(CALIBRATION_KEY);
    } catch {
      // storage blocked: nothing saved to clear
    }
    setOffset(null);
  }

  return (
    <Dialog open={open} onClose={onClose} title="SETTINGS" kao="(｀∀´)ﾉ☆">
      <section className="settings-row">
        <div className="settings-row__text">
          <h3 className="settings-row__title">MENU MUSIC</h3>
          <p className="settings-row__hint">Plays on the menus and stops whenever the mic is in use.</p>
        </div>
        {music.available ? (
          <PixelButton tone={music.muted ? 'paper' : 'butter'} aria-pressed={!music.muted} onClick={toggleMenuMusic}>
            {music.muted ? '♪ OFF' : '♪ ON'}
          </PixelButton>
        ) : (
          <span className="settings-row__off">NOT INSTALLED</span>
        )}
      </section>
      {!music.available && (
        <Notice tone="info">
          No track on this computer. Put one at <code>web/public/audio/menu-bgm.mp3</code> to hear it.
        </Notice>
      )}

      <section className="settings-row">
        <div className="settings-row__text">
          <h3 className="settings-row__title">TIMING CHECK</h3>
          <p className="settings-row__hint">
            {offset === null
              ? 'Not measured yet. Run it from song select with your headphones on.'
              : `Saved delay correction: ${Math.round(offset * 1000)} ms for this device.`}
          </p>
        </div>
        <PixelButton tone="paper" disabled={offset === null} onClick={resetTiming}>
          RESET
        </PixelButton>
      </section>
    </Dialog>
  );
}
