import React from 'react'
import Icon from '@mdi/react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { IconButton } from '../../components/ui/IconButton.jsx'
import { findIconPath, DEFAULT_REMOTE_ICON } from '../../icons/iconRegistry.js'
import { mdiPencilOutline, mdiTrashCanOutline } from '@mdi/js'

export function RemoteTile({ remote, onEdit, onDelete }) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const iconKey = remote.icon || DEFAULT_REMOTE_ICON

  return (
    <div
      className="rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-[var(--shadow)] p-4 flex items-center justify-between gap-3 cursor-pointer transition-shadow hover:shadow-[0_14px_30px_rgba(2,6,23,0.12)]"
      onClick={() => navigate(`/remotes/${remote.id}`, { state: { from: '/remotes' } })}
      role="button"
      tabIndex={0}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="h-12 w-12 rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] flex items-center justify-center">
          <Icon path={findIconPath(iconKey)} size={1.2} />
        </div>
        <div className="min-w-0">
          <div className="font-semibold truncate">{remote.name}</div>
          <div className="text-xs text-[rgb(var(--muted))] truncate">#{remote.id}</div>
        </div>
      </div>

      <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
        <IconButton label={t('common.edit')} onClick={() => onEdit(remote)}>
          <Icon path={mdiPencilOutline} size={1} />
        </IconButton>
        <IconButton label={t('common.delete')} onClick={() => onDelete(remote)}>
          <Icon path={mdiTrashCanOutline} size={1} />
        </IconButton>
      </div>
    </div>
  )
}
