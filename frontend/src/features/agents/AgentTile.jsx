import React from 'react'
import Icon from '@mdi/react'
import { useNavigate } from 'react-router-dom'
import { mdiCheck, mdiPencilOutline, mdiRestart, mdiTrashCanOutline, mdiUploadOutline } from '@mdi/js'
import { useTranslation } from 'react-i18next'

import { IconButton } from '../../components/ui/IconButton.jsx'
import { Badge } from '../../components/ui/Badge.jsx'
import { DEFAULT_AGENT_ICON, findIconPath } from '../../icons/iconRegistry.js'
import {
  installationBadgeLabel,
  installationBadgeVariant,
  isInstallationInProgress,
  normalizeInstallationStatus,
} from './installationStatus.js'

function agentTypeLabel(agentType, t) {
  if (agentType === 'esp32') return t('agents.typeEsp32')
  if (agentType === 'docker') return t('agents.typeDocker')
  if (agentType === 'local') return t('agents.typeLocal')
  return t('agents.typeUnknown')
}

export function AgentTile({ agent, onEdit, onDelete, onAccept, onUpdate, onReboot }) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const runtime = agent.runtime || {}
  const ota = agent.ota || {}
  const isOnline = String(agent.status || '').trim().toLowerCase() === 'online'
  const typeLabel = agentTypeLabel(String(runtime.agent_type || agent.agent_type || '').trim().toLowerCase(), t)
  const swVersion = String(runtime.sw_version || agent.sw_version || '').trim()
  const updateAvailable = Boolean(ota.update_available && ota.supported)
  const rebootRequired = Boolean(runtime.reboot_required || ota.reboot_required)
  const installation = agent.installation || {}
  const installationInProgress = isInstallationInProgress(installation)
  const installationStatus = normalizeInstallationStatus(installation)
  const installationLabel = installationBadgeLabel(installation)
  const showUpdateAvailable = updateAvailable && installationStatus === 'idle'

  return (
    <div
      className={[
        'rounded-2xl border bg-[rgb(var(--card))] shadow-[var(--shadow)] p-4 flex items-center justify-between gap-3 transition-shadow',
        agent.pending
          ? 'border-[rgb(var(--primary))] hover:shadow-[0_14px_30px_rgba(2,6,23,0.12)]'
          : 'border-[rgb(var(--border))] hover:shadow-[0_14px_30px_rgba(2,6,23,0.12)]',
      ].join(' ')}
      onClick={() => navigate(`/agent/${agent.agent_id}`, { state: { from: '/agents' } })}
      role="button"
      tabIndex={0}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="h-12 w-12 rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] flex items-center justify-center">
          <Icon path={findIconPath(agent.icon || DEFAULT_AGENT_ICON)} size={1.2} />
        </div>
        <div className="min-w-0">
          <div className="font-semibold truncate">{agent.name || agent.agent_id}</div>
          <div className="text-xs text-[rgb(var(--muted))] truncate">{agent.agent_id}</div>
          <div className="mt-1 flex items-center gap-2 flex-wrap">
            <Badge variant={isOnline ? 'success' : 'danger'}>
              {isOnline ? t('health.online') : t('health.offline')}
            </Badge>
            <Badge variant="neutral">{typeLabel}</Badge>
            {swVersion ? <Badge variant="neutral">v{swVersion}</Badge> : null}
            {installationLabel ? <Badge variant={installationBadgeVariant(installation)}>{installationLabel}</Badge> : null}
            {showUpdateAvailable ? <Badge variant="warning">{t('agents.updateAvailable')}</Badge> : null}
            {rebootRequired ? <Badge variant="warning">{t('agents.rebootRequired')}</Badge> : null}
          </div>
        </div>
      </div>

      <div className="flex gap-2" onClick={(event) => event.stopPropagation()}>
        {agent.pending ? (
          <IconButton label={t('common.confirm')} onClick={() => onAccept(agent)}>
            <Icon path={mdiCheck} size={1} />
          </IconButton>
        ) : (
          <>
            <IconButton label={t('common.edit')} onClick={() => onEdit(agent)}>
              <Icon path={mdiPencilOutline} size={1} />
            </IconButton>
            <IconButton label={t('common.delete')} onClick={() => onDelete(agent)}>
              <Icon path={mdiTrashCanOutline} size={1} />
            </IconButton>
            {updateAvailable && onUpdate ? (
              <IconButton label={t('agents.updateAction')} onClick={() => onUpdate?.(agent)} disabled={installationInProgress}>
                <Icon path={mdiUploadOutline} size={1} />
              </IconButton>
            ) : null}
            {rebootRequired ? (
              <IconButton label={t('agents.rebootAction')} onClick={() => onReboot?.(agent)} disabled={installationInProgress}>
                <Icon path={mdiRestart} size={1} />
              </IconButton>
            ) : null}
          </>
        )}
      </div>
    </div>
  )
}
