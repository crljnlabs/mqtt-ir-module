import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiChevronLeft, mdiTrashCanOutline, mdiPencilOutline, mdiPlus } from '@mdi/js'

import { listRemotes, updateRemote, deleteRemote } from '../api/remotesApi.js'
import { listButtons, updateButton, deleteButton, sendPress, sendHold } from '../api/buttonsApi.js'
import { getLearningStatus } from '../api/statusApi.js'
import { writeLocalStorage } from '../utils/storage.js'
import { listAgents } from '../api/agentsApi.js'

import { Card, CardBody, CardHeader, CardTitle } from '../components/ui/Card.jsx'
import { Button } from '../components/ui/Button.jsx'
import { IconButton } from '../components/ui/IconButton.jsx'
import { ConfirmDialog } from '../components/ui/ConfirmDialog.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'

import { RemoteEditorDrawer } from '../features/remotes/RemoteEditorDrawer.jsx'
import { ButtonTile } from '../features/buttons/ButtonTile.jsx'
import { HoldSendDialog } from '../features/buttons/HoldSendDialog.jsx'
import { LearningWizard } from '../features/learning/LearningWizard.jsx'
import { AgentPickerModal } from '../components/agents/AgentPickerModal.jsx'
import { ApiErrorMapper } from '../utils/apiErrorMapper.js'

function resolveLearningDisabledReason(remote, agents, t) {
  const assignedId = String(remote?.assigned_agent_id || '').trim()
  const onlineLearnCapable = (agents || []).filter(
    (agent) => agent?.status === 'online' && Boolean(agent?.capabilities?.can_learn),
  )

  if (!assignedId) {
    if (onlineLearnCapable.length === 0) {
      return t('wizard.noLearnCapableAgent')
    }
    return t('wizard.assignAgentFirst')
  }

  const assigned = (agents || []).find((agent) => String(agent?.agent_id || '') === assignedId)
  if (!assigned) {
    return t('wizard.assignedAgentMissing')
  }
  if (!assigned.capabilities?.can_learn) {
    return t('wizard.assignedAgentCannotLearn')
  }

  return ''
}

export function RemoteDetailPage() {
  const { t } = useTranslation()
  const toast = useToast()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const { remoteId } = useParams()
  const errorMapper = new ApiErrorMapper(t)

  const numericRemoteId = Number(remoteId)

  const learningStatusQuery = useQuery({ queryKey: ['status-learning'], queryFn: getLearningStatus })
  const remotesQuery = useQuery({ queryKey: ['remotes'], queryFn: listRemotes })
  const buttonsQuery = useQuery({ queryKey: ['buttons', numericRemoteId], queryFn: () => listButtons(numericRemoteId) })
  const agentsQuery = useQuery({ queryKey: ['agents'], queryFn: listAgents, staleTime: 30_000 })
  const agents = agentsQuery.data || []

  const remote = useMemo(() => {
    const list = remotesQuery.data || []
    return list.find((r) => Number(r.id) === numericRemoteId) || null
  }, [remotesQuery.data, numericRemoteId])

  useEffect(() => {
    if (numericRemoteId) writeLocalStorage('lastOpenedRemoteId', numericRemoteId)
  }, [numericRemoteId])

  const learningActive = Boolean(learningStatusQuery.data?.learn_enabled)
  const learningRemoteId = learningStatusQuery.data?.learn_remote_id ?? null
  const learningAgentId = String(learningStatusQuery.data?.learn_agent_id || '').trim()
  const assignedAgentId = String(remote?.assigned_agent_id || '').trim()
  const learningOnCurrentRemote = learningActive && Number(learningRemoteId) === Number(numericRemoteId)
  const learningOnAssignedAgent = Boolean(
    learningActive && learningAgentId && assignedAgentId && learningAgentId === assignedAgentId,
  )
  const sendingDisabled = learningOnCurrentRemote || learningOnAssignedAgent

  const [editRemoteOpen, setEditRemoteOpen] = useState(false)
  const [deleteRemoteOpen, setDeleteRemoteOpen] = useState(false)

  const [deleteButtonTarget, setDeleteButtonTarget] = useState(null)
  const [deleteAllButtonsOpen, setDeleteAllButtonsOpen] = useState(false)

  const [holdDialogOpen, setHoldDialogOpen] = useState(false)
  const [holdTarget, setHoldTarget] = useState(null)

  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardTargetButton, setWizardTargetButton] = useState(null)
  const [agentPickerOpen, setAgentPickerOpen] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const pendingActionRef = useRef(null)

  const resetHoldDialogState = () => {
    setHoldDialogOpen(false)
    setHoldTarget(null)
  }

  const resetWizardState = () => {
    setWizardOpen(false)
    setWizardTargetButton(null)
  }

  const resolveDefaultAgentId = () => {
    if (!agents.length) return ''
    const online = agents.find((agent) => agent.status === 'online')
    return (online || agents[0]).agent_id
  }

  const openAgentPicker = (retryAction) => {
    pendingActionRef.current = retryAction
    setSelectedAgentId(resolveDefaultAgentId())
    setAgentPickerOpen(true)
  }

  const closeAgentPicker = () => {
    pendingActionRef.current = null
    setAgentPickerOpen(false)
  }

  const deleteRemoteMutation = useMutation({
    mutationFn: () => deleteRemote(numericRemoteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('common.delete'), message: t('common.deleted') })
      navigate('/remotes')
    },
    onError: (e) => toast.show({ title: t('common.delete'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  const assignAgentMutation = useMutation({
    mutationFn: async (agentId) => {
      if (!remote) throw new Error(t('errors.notFoundTitle'))
      const payload = {
        ...remote,
        assigned_agent_id: agentId || null,
      }
      return updateRemote(remote.id, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      const retry = pendingActionRef.current
      pendingActionRef.current = null
      setAgentPickerOpen(false)
      if (retry) retry()
    },
    onError: (e) => toast.show({ title: t('agents.pickerTitle'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  const updateButtonMutation = useMutation({
    mutationFn: ({ buttonId, name, icon }) => updateButton(buttonId, { name, icon }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buttons', numericRemoteId] })
    },
    onError: (e) => toast.show({ title: t('button.title'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  const deleteButtonMutation = useMutation({
    mutationFn: (buttonId) => deleteButton(buttonId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buttons', numericRemoteId] })
      toast.show({ title: t('common.delete'), message: t('common.deleted') })
      setDeleteButtonTarget(null)
    },
    onError: (e) => toast.show({ title: t('common.delete'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  const deleteAllButtonsMutation = useMutation({
    mutationFn: async () => {
      const buttons = buttonsQuery.data || []
      await Promise.all(buttons.map((b) => deleteButton(b.id)))
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['buttons', numericRemoteId] })
      toast.show({ title: t('common.delete'), message: t('common.deleted') })
      setDeleteAllButtonsOpen(false)
    },
    onError: (e) => toast.show({ title: t('common.delete'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  const sendPressMutation = useMutation({
    mutationFn: (buttonId) => sendPress(buttonId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('button.send'), message: t('button.sendPressSuccess') })
    },
    onError: (error, buttonId) => {
      const info = errorMapper.getErrorInfo(error)
      if (info.code === 'agent_required') {
        openAgentPicker(() => sendPressMutation.mutate(buttonId))
        return
      }
      toast.show({ title: t('button.send'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const sendHoldMutation = useMutation({
    mutationFn: ({ buttonId, holdMs }) => sendHold(buttonId, holdMs),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('button.send'), message: t('button.sendHoldSuccess') })
    },
    onError: (error, variables) => {
      const info = errorMapper.getErrorInfo(error)
      if (info.code === 'agent_required') {
        openAgentPicker(() => sendHoldMutation.mutate(variables))
        return
      }
      toast.show({ title: t('button.send'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const existingButtons = buttonsQuery.data || []
  const hasExistingButtons = existingButtons.length > 0
  const learningBlocked = learningActive && Number(learningRemoteId) !== Number(numericRemoteId)
  const learningRemoteLabel = learningStatusQuery.data?.learn_remote_name || (learningRemoteId ? `#${learningRemoteId}` : '')
  const buttonsLoading = buttonsQuery.isLoading
  const learnDisabledReason = useMemo(() => {
    if (!remote) return ''
    return resolveLearningDisabledReason(remote, agents, t)
  }, [remote, agents, t])
  const wizardDisabled = learningBlocked || buttonsLoading || Boolean(learnDisabledReason)
  const backTarget = useMemo(() => {
    const fromState = location.state?.from
    if (typeof fromState === 'string' && fromState.trim()) return fromState
    return '/remotes'
  }, [location.state])

  const handleWizardRequest = () => {
    if (wizardDisabled) return
    const assignedId = String(remote?.assigned_agent_id || '').trim()
    const assigned = agents.find((a) => String(a?.agent_id || '') === assignedId)
    if (assigned && assigned.status !== 'online') {
      toast.show({ title: t('errors.agentOfflineTitle'), message: t('errors.agentOfflineBody') })
      return
    }
    setWizardTargetButton(null)
    setWizardOpen(true)
  }

  if (!remote) {
    return (
      <Card>
        <CardBody>
          <div className="text-sm text-[rgb(var(--muted))]">{t('errors.notFoundTitle')}</div>
        </CardBody>
      </Card>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center">
        <Button variant="ghost" size="sm" onClick={() => navigate(backTarget)}>
          <Icon path={mdiChevronLeft} size={0.9} />
          Back
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3">
            <span className="truncate">{remote.name}</span>
          </CardTitle>
          <div className="flex gap-2">
            <IconButton label={t('common.edit')} onClick={() => setEditRemoteOpen(true)}>
              <Icon path={mdiPencilOutline} size={1} />
            </IconButton>
            <IconButton label={t('common.delete')} onClick={() => setDeleteRemoteOpen(true)}>
              <Icon path={mdiTrashCanOutline} size={1} />
            </IconButton>
          </div>
        </CardHeader>
        <CardBody>
          <div className="text-xs text-[rgb(var(--muted))]">#{remote.id}</div>
          {learnDisabledReason ? (
            <div className="mt-2 text-sm text-[rgb(var(--muted))]">{learnDisabledReason}</div>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('remote.buttonsTitle')}</CardTitle>
          <div className="flex gap-2">
            <IconButton
              label={t('button.addButtons')}
              onClick={handleWizardRequest}
              title={learnDisabledReason || undefined}
              disabled={wizardDisabled}
            >
              <Icon path={mdiPlus} size={1} />
            </IconButton>
            <IconButton
              label={t('button.deleteAll')}
              onClick={() => setDeleteAllButtonsOpen(true)}
              disabled={!hasExistingButtons}
            >
              <Icon path={mdiTrashCanOutline} size={1} />
            </IconButton>
          </div>
        </CardHeader>
        <CardBody>
          {learningBlocked ? (
            <div className="mb-3 text-sm text-[rgb(var(--muted))]">
              {t('wizard.learningActiveElsewhere', { remote: learningRemoteLabel })}
            </div>
          ) : null}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-3">
            {existingButtons.map((b) => (
              <ButtonTile
                key={b.id}
                button={b}
                sendingDisabled={sendingDisabled}
                onSendPress={() => sendPressMutation.mutate(b.id)}
                onSendHold={() => {
                  setHoldTarget(b)
                  setHoldDialogOpen(true)
                }}
                onSave={(buttonId, updates) => updateButtonMutation.mutate({ buttonId, ...updates })}
                onDelete={setDeleteButtonTarget}
                onRelearn={(b) => {
                  setWizardTargetButton(b)
                  setWizardOpen(true)
                }}
              />
            ))}
          </div>
        </CardBody>
      </Card>

      <RemoteEditorDrawer open={editRemoteOpen} remote={remote} onClose={() => setEditRemoteOpen(false)} />

      <ConfirmDialog
        open={deleteRemoteOpen}
        title={t('remotes.deleteConfirmTitle')}
        body={t('remotes.deleteConfirmBody')}
        confirmText={t('common.delete')}
        onCancel={() => setDeleteRemoteOpen(false)}
        onConfirm={() => deleteRemoteMutation.mutate()}
      />

      <ConfirmDialog
        open={Boolean(deleteButtonTarget)}
        title={t('button.deleteConfirmTitle')}
        body={t('button.deleteConfirmBody')}
        confirmText={t('common.delete')}
        onCancel={() => setDeleteButtonTarget(null)}
        onConfirm={() => deleteButtonMutation.mutate(deleteButtonTarget.id)}
      />

      <ConfirmDialog
        open={deleteAllButtonsOpen}
        title={t('button.deleteAllConfirmTitle')}
        body={t('button.deleteAllConfirmBody')}
        confirmText={t('common.delete')}
        onCancel={() => setDeleteAllButtonsOpen(false)}
        onConfirm={() => deleteAllButtonsMutation.mutate()}
      />

      <HoldSendDialog
        open={holdDialogOpen}
        buttonName={holdTarget?.name || ''}
        defaultMs={1000}
        onClose={resetHoldDialogState}
        onSend={(ms) => {
          const buttonId = holdTarget?.id
          resetHoldDialogState()
          if (buttonId) sendHoldMutation.mutate({ buttonId, holdMs: ms })
        }}
      />

      <AgentPickerModal
        open={agentPickerOpen}
        agents={agents}
        selectedAgentId={selectedAgentId}
        onSelectAgent={setSelectedAgentId}
        onClose={closeAgentPicker}
        onConfirm={() => assignAgentMutation.mutate(selectedAgentId)}
        isSaving={assignAgentMutation.isPending}
      />

      <LearningWizard
        open={wizardOpen}
        remoteId={numericRemoteId}
        remoteName={remote.name}
        startExtend={true}
        targetButton={wizardTargetButton}
        existingButtons={existingButtons}
        onClose={resetWizardState}
        onAgentRequired={(retry) => openAgentPicker(retry)}
      />
    </div>
  )
}
