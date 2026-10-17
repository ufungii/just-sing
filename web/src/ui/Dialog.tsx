import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';
import { PixelButton } from './index';

/**
 * A pixel-styled modal built on the native <dialog>: it traps focus, closes on Escape and on a
 * click outside the panel, and hands focus back to whatever opened it.
 */
export function Dialog({
  open,
  onClose,
  title,
  kao,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  kao?: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      className="ui-dialog"
      aria-label={title}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose(); // the backdrop, not the panel
      }}
    >
      {open && (
        <div className="ui-dialog__panel">
          <header className="ui-dialog__head">
            <h2 className="ui-dialog__title">{title}</h2>
            {kao && (
              <span className="ui-kao ui-dialog__kao" aria-hidden="true">
                {kao}
              </span>
            )}
            <PixelButton tone="paper" size="sm" className="ui-dialog__close" aria-label="Close" onClick={onClose}>
              X
            </PixelButton>
          </header>
          {children}
        </div>
      )}
    </dialog>
  );
}
