import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiChevronLeft, mdiDotsHorizontal, mdiLinkPlus, mdiPencilOutline, mdiPlus, mdiRestart, mdiTextBoxSearchOutline, mdiTrashCanOutline } from '@mdi/js'

import { deleteAgent, getAgent, rebootAgent } from '../api/agentsApi.js'
import { createRemote, deleteRemote, listRemotes, updateRemote } from '../api/remotesApi.js'
import { Card, CardBody, CardHeader, CardTitle } from '../components/ui/Card.jsx'
import { Button } from '../components/ui/Button.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { IconButton } from '../components/ui/IconButton.jsx'
import { ConfirmDialog } from '../components/ui/ConfirmDialog.jsx'
import { Drawer } from '../components/ui/Drawer.jsx'
import { Modal } from '../components/ui/Modal.jsx'
import { TextField } from '../components/ui/TextField.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../utils/apiErrorMapper.js'
import { AgentEditorDrawer } from '../features/agents/AgentEditorDrawer.jsx'
import { RemoteEditorDrawer } from '../features/remotes/RemoteEditorDrawer.jsx'
import { DEFAULT_REMOTE_ICON, findIconPath } from '../icons/iconRegistry.js'
import {
  installationBadgeLabel,
  installationBadgeVariant,
  isInstallationInProgress,
} from '../features/agents/installationStatus.js'

export function AgentPage() {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const errorMapper = new ApiErrorMapper(t)
  const { agentId = '' } = useParams()
  const normalizedAgentId = String(agentId || '').trim()

  const agentQuery = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => getAgent(agentId),
    enabled: Boolean(agentId),
    refetchInterval: 5000,
  })
  const remotesQuery = useQuery({ queryKey: ['remotes'], queryFn: listRemotes })
  const [editOpen, setEditOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [createRemoteOpen, setCreateRemoteOpen] = useState(false)
  const [assignRemoteOpen, setAssignRemoteOpen] = useState(false)
  const [newRemoteName, setNewRemoteName] = useState('')
  const [menuRemote, setMenuRemote] = useState(null)
  const [editRemote, setEditRemote] = useState(null)
  const [deleteRemoteTarget, setDeleteRemoteTarget] = useState(null)
  const [assigningRemoteId, setAssigningRemoteId] = useState(null)

  const handleCreateRemoteClose = () => {
    setCreateRemoteOpen(false)
    setNewRemoteName('')
  }

  const deleteAgentMutation = useMutation({
    mutationFn: () => deleteAgent(agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('common.delete'), message: t('common.deleted') })
      navigate('/agents')
    },
    onError: (error) => {
      toast.show({ title: t('common.delete'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const rebootMutation = useMutation({
    mutationFn: () => rebootAgent(agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agent', agentId] })
      toast.show({ title: t('agents.rebootAction'), message: t('agents.rebootRequested') })
    },
    onError: (error) => {
      toast.show({ title: t('agents.rebootAction'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const createRemoteMutation = useMutation({
    mutationFn: async () => {
      const created = await createRemote({ name: newRemoteName.trim(), icon: null })
      return updateRemote(created.id, {
        ...created,
        assigned_agent_id: agentId || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('remotes.create'), message: t('common.saved') })
      handleCreateRemoteClose()
    },
    onError: (error) => {
      toast.show({ title: t('remotes.create'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const deleteRemoteMutation = useMutation({
    mutationFn: (remoteId) => deleteRemote(remoteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('common.delete'), message: t('common.deleted') })
      setDeleteRemoteTarget(null)
    },
    onError: (error) => {
      toast.show({ title: t('common.delete'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const assignedRemotes = useMemo(() => {
    const remotes = remotesQuery.data || []
    return remotes.filter((remote) => String(remote.assigned_agent_id || '').trim() === normalizedAgentId)
  }, [remotesQuery.data, normalizedAgentId])

  const assignableRemotes = useMemo(() => {
    const remotes = remotesQuery.data || []
    return remotes
      .map((remote) => {
        const assignedAgentId = String(remote.assigned_agent_id || '').trim()
        return {
          remote,
          assignedAgentId,
          isUnassigned: !assignedAgentId,
        }
      })
      .filter(({ assignedAgentId }) => assignedAgentId !== normalizedAgentId)
      .sort((a, b) => {
        if (a.isUnassigned !== b.isUnassigned) {
          return a.isUnassigned ? -1 : 1
        }
        const nameCompare = String(a.remote.name || '').localeCompare(String(b.remote.name || ''), undefined, {
          sensitivity: 'base',
          numeric: true,
        })
        if (nameCompare !== 0) return nameCompare
        return Number(a.remote.id) - Number(b.remote.id)
      })
  }, [remotesQuery.data, normalizedAgentId])

  const assignableRemoteGroups = useMemo(
    () =>
      [
        {
          key: 'unassigned',
          title: t('agents.assignExistingRemoteSuggestedTitle'),
          items: assignableRemotes.filter((candidate) => candidate.isUnassigned),
        },
        {
          key: 'assigned',
          title: t('agents.assignExistingRemoteOtherTitle'),
          items: assignableRemotes.filter((candidate) => !candidate.isUnassigned),
        },
      ].filter((group) => group.items.length > 0),
    [assignableRemotes, t],
  )

  const assignRemoteMutation = useMutation({
    mutationFn: (remote) =>
      updateRemote(remote.id, {
        ...remote,
        assigned_agent_id: normalizedAgentId || null,
      }),
    onMutate: (remote) => {
      setAssigningRemoteId(Number(remote.id))
    },
    onSuccess: (_, remote) => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('agents.assignExistingRemoteAction'), message: t('agents.assignExistingRemoteSuccess', { name: remote.name }) })
    },
    onError: (error) => {
      toast.show({ title: t('agents.assignExistingRemoteAction'), message: errorMapper.getMessage(error, 'common.failed') })
    },
    onSettled: () => {
      setAssigningRemoteId(null)
    },
  })

  const isLoading = agentQuery.isLoading
  const hasAgent = Boolean(agentQuery.data)
  const backTarget = useMemo(() => {
    const fromState = location.state?.from
    if (typeof fromState === 'string' && fromState.trim()) return fromState
    return '/agents'
  }, [location.state])

  if (isLoading) {
    return (
      <Card>
        <CardBody>
          <div className="text-sm text-[rgb(var(--muted))]">{t('common.loading')}</div>
        </CardBody>
      </Card>
    )
  }

  if (agentQuery.isError || !hasAgent) {
    return (
      <Card>
        <CardBody className="space-y-3">
          <div className="text-sm text-[rgb(var(--muted))]">{t('errors.notFoundTitle')}</div>
          <div>
            <Button variant="secondary" onClick={() => navigate('/settings')}>
              {t('settings.agentTitle')}
            </Button>
          </div>
        </CardBody>
      </Card>
    )
  }

  const agent = agentQuery.data
  const agentLabel = agent.name || agent.agent_id
  const runtime = agent.runtime || {}
  const rebootRequired = Boolean(runtime.reboot_required || agent.ota?.reboot_required)
  const isOnline = String(agent.status || '').trim().toLowerCase() === 'online'
  const installation = agent.installation || {}
  const installationInProgress = isInstallationInProgress(installation)
  const installationLabel = installationBadgeLabel(installation)
  const agentType = String(runtime.agent_type || agent.agent_type || '').trim().toLowerCase()
  const swVersion = String(runtime.sw_version || agent.sw_version || '').trim()
  const typeLabel =
    agentType === 'esp32'
      ? t('agents.typeEsp32')
      : agentType === 'docker'
        ? t('agents.typeDocker')
        : agentType === 'local'
          ? t('agents.typeLocal')
          : t('agents.typeUnknown')

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
            <span className="truncate">{agentLabel}</span>
          </CardTitle>
          <div className="flex gap-2">
            <IconButton
              label="Logs"
              onClick={() => navigate(`/agent/${agent.agent_id}/logs`, { state: { from: location.pathname } })}
            >
              <Icon path={mdiTextBoxSearchOutline} size={1} />
            </IconButton>
            {rebootRequired ? (
              <IconButton
                label={t('agents.rebootAction')}
                onClick={() => rebootMutation.mutate()}
                disabled={rebootMutation.isPending || installationInProgress}
              >
                <Icon path={mdiRestart} size={1} />
              </IconButton>
            ) : null}
            <IconButton label={t('common.edit')} onClick={() => setEditOpen(true)} disabled={installationInProgress}>
              <Icon path={mdiPencilOutline} size={1} />
            </IconButton>
            <IconButton label={t('common.delete')} onClick={() => setDeleteOpen(true)} disabled={installationInProgress}>
              <Icon path={mdiTrashCanOutline} size={1} />
            </IconButton>
          </div>
        </CardHeader>
        <CardBody>
          <div className="text-xs text-[rgb(var(--muted))]">
            {t('agents.agentIdLabel')}: {agent.agent_id}
          </div>
          <div className="text-xs text-[rgb(var(--muted))] mt-1">
            {t('agents.typeLabel')}: {typeLabel}
            {swVersion ? ` · v${swVersion}` : ''}
          </div>
          <div className="mt-2">
            <Badge variant={isOnline ? 'success' : 'danger'}>
              {isOnline ? t('health.online') : t('health.offline')}
            </Badge>
            {installationLabel ? (
              <span className="ml-2">
                <Badge variant={installationBadgeVariant(installation)}>{installationLabel}</Badge>
              </span>
            ) : null}
          </div>
          {installationInProgress ? (
            <div className="text-xs text-amber-600 mt-1">{installation.message || t('common.loading')}</div>
          ) : null}
          {rebootRequired ? (
            <div className="text-xs text-amber-600 mt-1">{t('agents.rebootRequired')}</div>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('agents.assignedRemotesTitle')}</CardTitle>
          <div className="flex items-center gap-2">
            <IconButton label={t('agents.assignExistingRemoteAction')} onClick={() => setAssignRemoteOpen(true)}>
              <Icon path={mdiLinkPlus} size={1} />
            </IconButton>
            <IconButton label={t('remotes.create')} onClick={() => setCreateRemoteOpen(true)}>
              <Icon path={mdiPlus} size={1} />
            </IconButton>
          </div>
        </CardHeader>
        <CardBody>
          {assignedRemotes.length === 0 ? (
            <div className="text-sm text-[rgb(var(--muted))]">{t('agents.assignedRemotesEmpty')}</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {assignedRemotes.map((remote) => (
                <div
                  key={remote.id}
                  className="group rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] p-3 text-left shadow-[var(--shadow)] hover:shadow-[0_14px_30px_rgba(2,6,23,0.12)] cursor-pointer flex flex-col gap-2 transition-shadow"
                  onClick={() => navigate(`/remotes/${remote.id}`, { state: { from: location.pathname } })}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      navigate(`/remotes/${remote.id}`, { state: { from: location.pathname } })
                    }
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="h-14 w-14 rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] flex items-center justify-center">
                      <Icon path={findIconPath(remote.icon || DEFAULT_REMOTE_ICON)} size={1.4} />
                    </div>
                    <div onClick={(event) => event.stopPropagation()}>
                      <IconButton label={t('common.menu')} onClick={() => setMenuRemote(remote)} className="h-9 w-9 opacity-80 group-hover:opacity-100">
                        <Icon path={mdiDotsHorizontal} size={1} />
                      </IconButton>
                    </div>
                  </div>
                  <div className="min-w-0">
                    <div className="font-semibold truncate px-2">{remote.name}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {editOpen ? <AgentEditorDrawer key={agent.agent_id} agent={agent} onClose={() => setEditOpen(false)} /> : null}
      <RemoteEditorDrawer open={Boolean(editRemote)} remote={editRemote} onClose={() => setEditRemote(null)} />

      <ConfirmDialog
        open={deleteOpen}
        title={t('common.delete')}
        body={`${agentLabel} (${agent.agent_id})`}
        confirmText={t('common.delete')}
        onCancel={() => setDeleteOpen(false)}
        onConfirm={() => deleteAgentMutation.mutate()}
      />

      <ConfirmDialog
        open={Boolean(deleteRemoteTarget)}
        title={t('remotes.deleteConfirmTitle')}
        body={t('remotes.deleteConfirmBody')}
        confirmText={t('common.delete')}
        onCancel={() => setDeleteRemoteTarget(null)}
        onConfirm={() => {
          if (!deleteRemoteTarget) return
          deleteRemoteMutation.mutate(deleteRemoteTarget.id)
        }}
      />

      <Drawer open={Boolean(menuRemote)} title={menuRemote?.name || ''} onClose={() => setMenuRemote(null)}>
        <div className="space-y-2">
          <Button
            variant="secondary"
            className="w-full justify-start"
            onClick={() => {
              setEditRemote(menuRemote)
              setMenuRemote(null)
            }}
          >
            <Icon path={mdiPencilOutline} size={1} />
            {t('common.edit')}
          </Button>
          <Button
            variant="danger"
            className="w-full justify-start"
            onClick={() => {
              setDeleteRemoteTarget(menuRemote)
              setMenuRemote(null)
            }}
          >
            <Icon path={mdiTrashCanOutline} size={1} />
            {t('common.delete')}
          </Button>
        </div>
      </Drawer>

      <Modal
        open={assignRemoteOpen}
        title={t('agents.assignExistingRemoteTitle')}
        onClose={() => setAssignRemoteOpen(false)}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => setAssignRemoteOpen(false)}>
              {t('common.close')}
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <div className="text-sm text-[rgb(var(--muted))]">{t('agents.assignExistingRemoteDescription')}</div>
          {assignableRemotes.length === 0 ? (
            <div className="text-sm text-[rgb(var(--muted))]">{t('agents.assignExistingRemoteEmpty')}</div>
          ) : (
            <div className="space-y-3">
              {assignableRemoteGroups.map((group) => (
                <div key={group.key} className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wide text-[rgb(var(--muted))]">{group.title}</div>
                  <div className="space-y-2">
                    {group.items.map((candidate) => {
                      const remote = candidate.remote
                      const remoteId = Number(remote.id)
                      return (
                        <div
                          key={remote.id}
                          className="rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] px-3 py-2 flex items-center justify-between gap-3"
                        >
                          <div className="min-w-0">
                            <div className="font-medium truncate">{remote.name}</div>
                            <div className="text-xs text-[rgb(var(--muted))] truncate">
                              #{remote.id}
                              {candidate.isUnassigned
                                ? ` · ${t('agents.unassigned')}`
                                : ` · ${t('agents.assignExistingRemoteAssignedTo', { id: candidate.assignedAgentId })}`}
                            </div>
                          </div>
                          <Button
                            size="sm"
                            onClick={() => assignRemoteMutation.mutate(remote)}
                            disabled={assignRemoteMutation.isPending}
                          >
                            {assigningRemoteId === remoteId ? t('common.loading') : t('agents.assignExistingRemoteAssignButton')}
                          </Button>
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Modal>

      <Modal
        open={createRemoteOpen}
        title={t('remotes.create')}
        onClose={handleCreateRemoteClose}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={handleCreateRemoteClose}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => createRemoteMutation.mutate()} disabled={!newRemoteName.trim() || createRemoteMutation.isPending}>
              {t('common.save')}
            </Button>
          </div>
        }
      >
        <TextField label={t('remotes.name')} value={newRemoteName} onChange={(event) => setNewRemoteName(event.target.value)} />
      </Modal>
    </div>
  )
}
