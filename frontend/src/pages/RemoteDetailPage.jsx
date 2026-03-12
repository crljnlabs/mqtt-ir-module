import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiChevronLeft, mdiTrashCanOutline, mdiPencilOutline, mdiMagicStaff } from '@mdi/js'

import { listRemotes, updateRemote, deleteRemote } from '../api/remotesApi.js'
import { listButtons, updateButton, deleteButton, sendPress, sendHold } from '../api/buttonsApi.js'
import { getLearningStatus } from '../api/statusApi.js'
import { writeLocalStorage } from '../utils/storage.js'
import { listAgents } from '../api/agentsApi.js'

import { Card, CardBody, CardHeader, CardTitle } from '../components/ui/Card.jsx'
import { Button } from '../components/ui/Button.jsx'
import { IconButton } from '../components/ui/IconButton.jsx'
import { ConfirmDialog } from '../components/ui/ConfirmDialog.jsx'
import { Modal } from '../components/ui/Modal.jsx'
import { TextField } from '../components/ui/TextField.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'

import { RemoteEditorDrawer } from '../features/remotes/RemoteEditorDrawer.jsx'
import { ButtonTile } from '../features/buttons/ButtonTile.jsx'
import { HoldSendDialog } from '../features/buttons/HoldSendDialog.jsx'
import { IconPicker } from '../components/pickers/IconPicker.jsx'
import { DEFAULT_BUTTON_ICON } from '../icons/iconRegistry.js'
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
  if (assigned.status !== 'online') {
    return t('wizard.assignedAgentOffline')
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

  const [renameTarget, setRenameTarget] = useState(null)
  const [renameValue, setRenameValue] = useState('')

  const [iconTarget, setIconTarget] = useState(null)
  const [iconPickerOpen, setIconPickerOpen] = useState(false)

  const [deleteButtonTarget, setDeleteButtonTarget] = useState(null)

  const [holdDialogOpen, setHoldDialogOpen] = useState(false)
  const [holdTarget, setHoldTarget] = useState(null)

  const [wizardOpen, setWizardOpen] = useState(false)
  const [wizardExtend, setWizardExtend] = useState(true)
  const [wizardTargetButton, setWizardTargetButton] = useState(null)
  const [learningChoiceOpen, setLearningChoiceOpen] = useState(false)
  const [agentPickerOpen, setAgentPickerOpen] = useState(false)
  const [selectedAgentId, setSelectedAgentId] = useState('')
  const pendingActionRef = useRef(null)

  const resetRenameState = () => {
    // Reset rename modal state when it closes.
    setRenameTarget(null)
    setRenameValue('')
  }

  const resetIconPickerState = () => {
    // Reset icon picker state when it closes.
    setIconPickerOpen(false)
    setIconTarget(null)
  }

  const resetHoldDialogState = () => {
    // Reset hold dialog state when it closes.
    setHoldDialogOpen(false)
    setHoldTarget(null)
  }

  const resetWizardState = () => {
    // Reset wizard entry state so the next open starts fresh.
    setWizardOpen(false)
    setWizardExtend(true)
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
      toast.show({ title: t('common.save'), message: t('common.saved') })
      resetRenameState()
      resetIconPickerState()
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

  // Centralize wizard setup so every entry point uses the same state reset.
  const startWizard = (extend) => {
    setWizardTargetButton(null)
    setWizardExtend(extend)
    setWizardOpen(true)
  }

  // Decide between immediate start or the choice dialog based on existing buttons.
  const handleWizardRequest = () => {
    if (wizardDisabled) return
    if (!hasExistingButtons) {
      startWizard(true)
      return
    }
    setLearningChoiceOpen(true)
  }

  const handleWizardChoice = (extend) => {
    setLearningChoiceOpen(false)
    startWizard(extend)
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
            <Button
              variant="secondary"
              size="sm"
              onClick={handleWizardRequest}
              title={learnDisabledReason || undefined}
              disabled={wizardDisabled}
            >
              <Icon path={mdiMagicStaff} size={1} />
              {t('remote.learnWizard')}
            </Button>
          </div>
        </CardHeader>
        <CardBody>
          {learningBlocked ? (
            <div className="mb-3 text-sm text-[rgb(var(--muted))]">
              {t('wizard.learningActiveElsewhere', { remote: learningRemoteLabel })}
            </div>
          ) : null}
          {/* Mobile-first grid: keep one column until the small breakpoint. */}
          <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-4 gap-3">
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
                onRename={() => {
                  setRenameTarget(b)
                  setRenameValue(b.name)
                }}
                onChangeIcon={() => {
                  setIconTarget(b)
                  setIconPickerOpen(true)
                }}
                onDelete={() => setDeleteButtonTarget(b)}
                onRelearn={() => {
                  setWizardTargetButton(b)
                  setWizardExtend(true)
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

      <Modal
        open={learningChoiceOpen}
        title={t('remote.learningChoiceTitle')}
        onClose={() => setLearningChoiceOpen(false)}
        footer={
          <div className="flex justify-end">
            <Button variant="secondary" onClick={() => setLearningChoiceOpen(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        }
      >
        <p className="text-sm text-[rgb(var(--muted))]">{t('remote.learningChoiceBody')}</p>
        <div className="mt-4 grid gap-2">
          <Button
            variant="secondary"
            className="w-full justify-start text-left"
            onClick={() => handleWizardChoice(true)}
          >
            <div className="flex flex-col items-start">
              <span className="font-semibold">{t('remote.learningChoiceAddTitle')}</span>
              <span className="text-xs text-[rgb(var(--muted))]">{t('remote.learningChoiceAddHint')}</span>
            </div>
          </Button>
          <Button
            variant="danger"
            className="w-full justify-start text-left"
            onClick={() => handleWizardChoice(false)}
          >
            <div className="flex flex-col items-start">
              <span className="font-semibold">{t('remote.learningChoiceResetTitle')}</span>
              <span className="text-xs text-white/90">{t('remote.learningChoiceResetHint')}</span>
            </div>
          </Button>
        </div>
      </Modal>

      <Modal
        open={Boolean(renameTarget)}
        title={t('button.rename')}
        onClose={resetRenameState}
        onConfirm={() => { if (renameValue.trim() && !updateButtonMutation.isPending) updateButtonMutation.mutate({ buttonId: renameTarget.id, name: renameValue.trim(), icon: renameTarget.icon }) }}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={resetRenameState}>
              {t('common.cancel')}
            </Button>
            <Button
              onClick={() => updateButtonMutation.mutate({ buttonId: renameTarget.id, name: renameValue.trim(), icon: renameTarget.icon })}
              disabled={!renameValue.trim() || updateButtonMutation.isPending}
            >
              {t('common.save')}
            </Button>
          </div>
        }
      >
        <TextField value={renameValue} onChange={(e) => setRenameValue(e.target.value)} label={t('wizard.buttonName')} />
      </Modal>

      <IconPicker
        open={iconPickerOpen}
        title={t('button.changeIcon')}
        initialIconKey={iconTarget?.icon || DEFAULT_BUTTON_ICON}
        onClose={resetIconPickerState}
        onSelect={(key) => {
          updateButtonMutation.mutate({ buttonId: iconTarget.id, name: iconTarget.name, icon: key })
        }}
      />

      <ConfirmDialog
        open={Boolean(deleteButtonTarget)}
        title={t('button.deleteConfirmTitle')}
        body={t('button.deleteConfirmBody')}
        confirmText={t('common.delete')}
        onCancel={() => setDeleteButtonTarget(null)}
        onConfirm={() => deleteButtonMutation.mutate(deleteButtonTarget.id)}
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
        startExtend={wizardExtend}
        targetButton={wizardTargetButton}
        existingButtons={existingButtons}
        onClose={resetWizardState}
        onAgentRequired={(retry) => openAgentPicker(retry)}
      />
    </div>
  )
}
