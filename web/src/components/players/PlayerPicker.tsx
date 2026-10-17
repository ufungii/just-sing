import { useEffect, useId, useRef, useState } from 'react';
import type { KeyboardEvent } from 'react';
import { rememberPlayer, usePlayers } from '../../lib/players';
import { PixelAvatar } from './PixelAvatar';
import { ProfileDialog } from './ProfileDialog';
import './players.css';

/**
 * Dropdown of this device's players, each with their avatar, plus "+ add player" at the bottom.
 * `disabledId` greys out a player already taken (the other seat in a battle).
 */
export function PlayerPicker({
  label,
  value,
  onChange,
  disabledId = null,
}: {
  label: string;
  value: string | null;
  onChange: (id: string) => void;
  disabledId?: string | null;
}) {
  const { players } = usePlayers();
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [adding, setAdding] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const labelId = useId();

  const chosen = players.find((p) => p.id === value) ?? null;
  // Options: every player, then the "add" row.
  const count = players.length + 1;

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener('pointerdown', away);
    return () => window.removeEventListener('pointerdown', away);
  }, [open]);

  function openList() {
    setActive(Math.max(0, players.findIndex((p) => p.id === value)));
    setOpen(true);
  }

  function choose(i: number) {
    if (i === players.length) {
      setOpen(false);
      setAdding(true);
      return;
    }
    const p = players[i];
    if (!p || p.id === disabledId) return;
    onChange(p.id);
    rememberPlayer(p.id);
    setOpen(false);
  }

  function onKeyDown(e: KeyboardEvent) {
    if (!open) {
      if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(e.key)) {
        e.preventDefault();
        openList();
      }
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      setActive((a) => (a + (e.key === 'ArrowDown' ? 1 : -1) + count) % count);
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      choose(active);
    } else if (e.key === 'Tab') {
      setOpen(false);
    }
  }

  return (
    <div className="picker" ref={rootRef}>
      <span className="picker__label" id={labelId}>
        {label}
      </span>
      <button
        type="button"
        className={`picker__button${open ? ' is-open' : ''}`}
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-labelledby={labelId}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
      >
        {chosen ? (
          <>
            <PixelAvatar avatar={chosen.avatar} size={40} />
            <span className="picker__name">{chosen.name}</span>
          </>
        ) : (
          <span className="picker__name picker__name--empty">{players.length ? 'Pick a player' : 'Add a player'}</span>
        )}
        <span className="picker__caret" aria-hidden="true">
          ▼
        </span>
      </button>

      {open && (
        <ul className="picker__list" id={listId} role="listbox" aria-labelledby={labelId}>
          {players.map((p, i) => {
            const taken = p.id === disabledId;
            return (
              <li
                key={p.id}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={p.id === value}
                aria-disabled={taken || undefined}
                className={`picker__option${i === active ? ' is-active' : ''}${p.id === value ? ' is-chosen' : ''}${taken ? ' is-taken' : ''}`}
                onPointerEnter={() => setActive(i)}
                onClick={() => choose(i)}
              >
                <PixelAvatar avatar={p.avatar} size={36} />
                <span className="picker__name">{p.name}</span>
                {taken && <span className="picker__tag">TAKEN</span>}
                {p.id === value && <span className="picker__tag">PICKED</span>}
              </li>
            );
          })}
          <li
            id={`${listId}-${players.length}`}
            role="option"
            aria-selected={false}
            className={`picker__option picker__option--add${active === players.length ? ' is-active' : ''}`}
            onPointerEnter={() => setActive(players.length)}
            onClick={() => choose(players.length)}
          >
            <span className="picker__plus" aria-hidden="true">
              +
            </span>
            <span className="picker__name">ADD PLAYER</span>
          </li>
        </ul>
      )}

      <ProfileDialog
        open={adding}
        startAdding
        onClose={() => setAdding(false)}
        onAdded={(p) => {
          onChange(p.id);
          setAdding(false);
        }}
      />
    </div>
  );
}
