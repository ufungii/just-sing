import { useEffect, useState } from 'react';
import { AVATAR_IDS, PLAYER_NAME_MAX, addPlayer, nameProblem, removePlayer, updatePlayer, usePlayers } from '../../lib/players';
import type { AvatarId, Player } from '../../lib/players';
import { Notice, PixelButton } from '../../ui';
import { Dialog } from '../../ui/Dialog';
import { PixelAvatar, avatarLabel } from './PixelAvatar';
import './players.css';

type Editing = { kind: 'none' } | { kind: 'new' } | { kind: 'edit'; id: string };

/**
 * Manage the players on this device: add, rename, pick an avatar, remove.
 * `startAdding` opens straight on the new-player form (used by the setup dropdowns);
 * `onAdded` hears about the player just created, so a dropdown can select them.
 */
export function ProfileDialog({
  open,
  onClose,
  startAdding = false,
  onAdded,
}: {
  open: boolean;
  onClose: () => void;
  startAdding?: boolean;
  onAdded?: (p: Player) => void;
}) {
  const { players } = usePlayers();
  const [editing, setEditing] = useState<Editing>({ kind: 'none' });
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);

  useEffect(() => {
    if (open) setEditing(startAdding || players.length === 0 ? { kind: 'new' } : { kind: 'none' });
    setConfirmRemove(null);
  }, [open]); // only when the dialog opens, not on every player change

  const current = editing.kind === 'edit' ? players.find((p) => p.id === editing.id) ?? null : null;

  return (
    <Dialog open={open} onClose={onClose} title="PLAYERS" kao="(っ＾▽＾)っ">
      <p className="players-hint">Everyone who sings on this computer. Names show up in matches and history.</p>

      {players.length > 0 && (
        <ul className="players-list" role="list">
          {players.map((p) => (
            <li key={p.id} className={`players-row${current?.id === p.id ? ' is-editing' : ''}`}>
              <PixelAvatar avatar={p.avatar} size={48} />
              <span className="players-row__name">{p.name}</span>
              {confirmRemove === p.id ? (
                <span className="players-row__actions">
                  <span className="players-row__ask">Remove {p.name}?</span>
                  <PixelButton tone="hot" size="sm" onClick={() => { removePlayer(p.id); setConfirmRemove(null); if (current?.id === p.id) setEditing({ kind: 'none' }); }}>
                    YES
                  </PixelButton>
                  <PixelButton tone="paper" size="sm" onClick={() => setConfirmRemove(null)}>
                    NO
                  </PixelButton>
                </span>
              ) : (
                <span className="players-row__actions">
                  <PixelButton tone="sky" size="sm" onClick={() => setEditing({ kind: 'edit', id: p.id })} aria-label={`Edit ${p.name}`}>
                    EDIT
                  </PixelButton>
                  <PixelButton tone="paper" size="sm" onClick={() => setConfirmRemove(p.id)} aria-label={`Remove ${p.name}`}>
                    REMOVE
                  </PixelButton>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      {editing.kind === 'none' ? (
        <PixelButton tone="hot" onClick={() => setEditing({ kind: 'new' })}>
          + ADD PLAYER
        </PixelButton>
      ) : (
        <PlayerForm
          key={editing.kind === 'edit' ? editing.id : 'new'}
          player={current}
          onCancel={players.length ? () => setEditing({ kind: 'none' }) : undefined}
          onSave={(name, avatar) => {
            if (current) {
              updatePlayer(current.id, { name, avatar });
            } else {
              const added = addPlayer(name, avatar); // outside onAdded?.(…): that would skip it when no one listens
              onAdded?.(added);
            }
            setEditing({ kind: 'none' });
          }}
        />
      )}
    </Dialog>
  );
}

/** Name field plus the avatar choices, for a new player or an existing one. */
function PlayerForm({
  player,
  onSave,
  onCancel,
}: {
  player: Player | null;
  onSave: (name: string, avatar: AvatarId) => void;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(player?.name ?? '');
  const [avatar, setAvatar] = useState<AvatarId>(player?.avatar ?? 'bunny');
  const [tried, setTried] = useState(false);
  const problem = nameProblem(name, player?.id);

  return (
    <form
      className="players-form"
      onSubmit={(e) => {
        e.preventDefault();
        setTried(true);
        if (!problem) onSave(name, avatar);
      }}
    >
      <h3 className="players-form__title">{player ? `EDIT ${player.name.toUpperCase()}` : 'NEW PLAYER'}</h3>
      <label className="players-field">
        <span className="players-field__label">NAME</span>
        <input
          className="players-input"
          value={name}
          maxLength={PLAYER_NAME_MAX}
          autoFocus
          autoComplete="nickname"
          placeholder="e.g. Mina"
          onChange={(e) => setName(e.target.value)}
        />
      </label>

      <div className="players-field">
        <span className="players-field__label">AVATAR</span>
        <div className="players-avatars" role="group" aria-label="Avatar">
          {AVATAR_IDS.map((id) => (
            <button
              key={id}
              type="button"
              className={`players-avatar-choice${avatar === id ? ' is-picked' : ''}`}
              aria-pressed={avatar === id}
              aria-label={avatarLabel(id)}
              onClick={() => setAvatar(id)}
            >
              <PixelAvatar avatar={id} size={56} />
              <span className="players-avatar-choice__name">{avatarLabel(id).toUpperCase()}</span>
            </button>
          ))}
        </div>
      </div>

      {tried && problem && <Notice tone="warn">{problem}</Notice>}

      <div className="players-form__actions">
        <PixelButton type="submit" tone="hot">
          {player ? 'SAVE' : 'ADD PLAYER'}
        </PixelButton>
        {onCancel && (
          <PixelButton tone="paper" onClick={onCancel}>
            CANCEL
          </PixelButton>
        )}
      </div>
    </form>
  );
}
