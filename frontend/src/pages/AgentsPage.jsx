import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { deleteAgent, listAgents, otaUpdateAgent, rebootAgent } from '../api/agentsApi.js'
import { getFirmwareCatalog } from '../api/firmwareApi.js'
import { getMqttStatus } from '../api/statusApi.js'
import { acceptPairing, closePairing, getPairingStatus, openPairing } from '../api/pairingApi.js'
import { Card, CardBody, CardHeader, CardTitle } from '../components/ui/Card.jsx'
import { Button } from '../components/ui/Button.jsx'
import { ConfirmDialog } from '../components/ui/ConfirmDialog.jsx'
import { Modal } from '../components/ui/Modal.jsx'
import { SelectField } from '../components/ui/SelectField.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../utils/apiErrorMapper.js'
import { AgentTile } from '../features/agents/AgentTile.jsx'
import { AgentEditorDrawer } from '../features/agents/AgentEditorDrawer.jsx'
import { isInstallationInProgress } from '../features/agents/installationStatus.js'

export function AgentsPage() {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)
  const [editTarget, setEditTarget] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [deleteForce, setDeleteForce] = useState(false)
  const [rebootTarget, setRebootTarget] = useState(null)
  const [otaTarget, setOtaTarget] = useState(null)
  const [otaVersion, setOtaVersion] = useState('')
  const [nowMs, setNowMs] = useState(() => Date.now())

  useEffect(() => {
    const interval = setInterval(() => setNowMs(Date.now()), 1000)
    return () => clearInterval(interval)
  }, [])

  const mqttQuery = useQuery({
    queryKey: ['status-mqtt'],
    queryFn: getMqttStatus,
    refetchInterval: 5000,
  })
  const pairingQuery = useQuery({
    queryKey: ['status-pairing'],
    queryFn: getPairingStatus,
    refetchInterval: (query) => {
      const isOpen = Boolean(query.state.data?.open)
      return isOpen ? 1000 : 5000
    },
  })
  const pairingOpenLive = Boolean(pairingQuery.data?.open)
  const agentsQuery = useQuery({
    queryKey: ['agents'],
    queryFn: listAgents,
    refetchInterval: (query) => {
      const list = Array.isArray(query.state.data) ? query.state.data : []
      const hasInstallingAgent = list.some((agent) => isInstallationInProgress(agent?.installation))
      return pairingOpenLive || hasInstallingAgent ? 1000 : 5000
    },
  })
  const firmwareQuery = useQuery({
    queryKey: ['firmware', 'esp32'],
    queryFn: () => getFirmwareCatalog('esp32'),
    staleTime: 60_000,
  })

  const openPairingMutation = useMutation({
    mutationFn: openPairing,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status-pairing'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      toast.show({ title: t('agents.pairingTitle'), message: t('agents.pairingOpened') })
    },
    onError: (error) => {
      toast.show({ title: t('agents.pairingTitle'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const closePairingMutation = useMutation({
    mutationFn: closePairing,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status-pairing'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      toast.show({ title: t('agents.pairingTitle'), message: t('agents.pairingClosed') })
    },
    onError: (error) => {
      toast.show({ title: t('agents.pairingTitle'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const acceptPairingMutation = useMutation({
    mutationFn: (agentId) => acceptPairing(agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['status-pairing'] })
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      toast.show({ title: t('agents.pairingTitle'), message: t('common.saved') })
    },
    onError: (error) => {
      toast.show({ title: t('agents.pairingTitle'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const deleteAgentMutation = useMutation({
    mutationFn: ({ agentId, force }) => deleteAgent(agentId, { force }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('common.delete'), message: t('common.deleted') })
      setDeleteTarget(null)
      setDeleteForce(false)
    },
    onError: (error) => {
      toast.show({ title: t('common.delete'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const rebootMutation = useMutation({
    mutationFn: (agentId) => rebootAgent(agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      toast.show({ title: t('agents.rebootAction'), message: t('agents.rebootRequested') })
      setRebootTarget(null)
    },
    onError: (error) => {
      toast.show({ title: t('agents.rebootAction'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const otaMutation = useMutation({
    mutationFn: ({ agentId, version }) => otaUpdateAgent(agentId, { version }),
    onMutate: () => {
      setOtaTarget(null)
      setOtaVersion('')
      toast.show({ title: t('agents.updateAction'), message: t('agents.updateRequested') })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
    },
    onError: (error) => {
      if (isOtaTimeoutError(error)) {
        queryClient.invalidateQueries({ queryKey: ['agents'] })
        toast.show({ title: t('agents.updateAction'), message: t('agents.updateTimeoutHint') })
        return
      }
      toast.show({ title: t('agents.updateAction'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const mqttConnected = Boolean(mqttQuery.data?.connected)
  const mqttConfigured = Boolean(mqttQuery.data?.configured)
  const pairingOpen = Boolean(pairingQuery.data?.open)
  const pairingExpiresAt = Number(pairingQuery.data?.expires_at || 0)
  const agents = useMemo(() => {
    const list = agentsQuery.data || []
    return [...list].sort((a, b) => {
      const aPending = Boolean(a.pending)
      const bPending = Boolean(b.pending)
      if (aPending !== bPending) return aPending ? -1 : 1
      return String(a.name || a.agent_id).localeCompare(String(b.name || b.agent_id))
    })
  }, [agentsQuery.data])

  const pairingCountdown = useMemo(() => {
    if (!pairingOpen || !pairingExpiresAt) return ''
    const secondsLeft = Math.max(0, Math.ceil((pairingExpiresAt * 1000 - nowMs) / 1000))
    const minutes = Math.floor(secondsLeft / 60)
    const seconds = secondsLeft % 60
    return `${minutes}:${String(seconds).padStart(2, '0')}`
  }, [pairingOpen, pairingExpiresAt, nowMs])

  const pairingHeaderText = useMemo(() => {
    if (!mqttConfigured) return t('settings.mqttNotConfigured')
    if (!mqttConnected) return t('settings.mqttDisconnected')
    if (pairingOpen && pairingCountdown) return pairingCountdown
    return pairingOpen ? t('agents.pairingStatusOpen') : t('agents.pairingStatusClosed')
  }, [mqttConfigured, mqttConnected, pairingOpen, pairingCountdown, t])
  const pairingHeaderIsCountdown = mqttConfigured && mqttConnected && pairingOpen && Boolean(pairingCountdown)

  const pairingDisabled = !mqttConfigured || !mqttConnected
  const installableFirmwareOptions = useMemo(() => {
    const entries = firmwareQuery.data?.items || []
    return entries.filter((item) => Boolean(item.installable && item.ota_exists))
  }, [firmwareQuery.data])
  const latestInstallableVersion = String(firmwareQuery.data?.latest_installable_version || '').trim()

  const openOtaModal = (agent) => {
    if (isInstallationInProgress(agent?.installation)) {
      return
    }
    const preferred = String(agent?.ota?.latest_version || '').trim()
    if (preferred && installableFirmwareOptions.some((entry) => String(entry.version) === preferred)) {
      setOtaVersion(preferred)
    } else if (
      latestInstallableVersion &&
      installableFirmwareOptions.some((entry) => String(entry.version) === latestInstallableVersion)
    ) {
      setOtaVersion(latestInstallableVersion)
    } else {
      const firstVersion = String(installableFirmwareOptions[0]?.version || '').trim()
      setOtaVersion(firstVersion)
    }
    setOtaTarget(agent)
  }

  const actionPending =
    openPairingMutation.isPending ||
    closePairingMutation.isPending ||
    acceptPairingMutation.isPending ||
    deleteAgentMutation.isPending ||
    rebootMutation.isPending
  const deleteRequiresForce = isInstallationInProgress(deleteTarget?.installation)

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{t('agents.pairingTitle')}</CardTitle>
          <div className={`text-sm text-[rgb(var(--muted))]${pairingHeaderIsCountdown ? ' font-mono tabular-nums' : ''}`}>{pairingHeaderText}</div>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="text-sm text-[rgb(var(--muted))]">{t('agents.pairingMqttHelp')}</div>
          {mqttQuery.data?.last_error ? (
            <div className="text-sm text-red-600">{mqttQuery.data.last_error}</div>
          ) : null}
          {pairingDisabled ? (
            <div className="rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3 text-sm">
              <div>{t('agents.pairingDisabledHint')}</div>
              <div className="mt-2">
                <Link to="/settings" className="underline">{t('agents.openSettings')}</Link>
              </div>
            </div>
          ) : null}
          {pairingOpen ? (
            <Button
              variant="secondary"
              onClick={() => closePairingMutation.mutate()}
              disabled={pairingDisabled || actionPending}
            >
              {t('agents.stopPairing')}
            </Button>
          ) : (
            <Button
              onClick={() => openPairingMutation.mutate()}
              disabled={pairingDisabled || actionPending}
            >
              {t('agents.startPairing')}
            </Button>
          )}
        </CardBody>
      </Card>

      <section className="space-y-2">
        {agentsQuery.isLoading ? (
          <div className="flex items-center gap-2 text-sm text-[rgb(var(--muted))]">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-[rgb(var(--muted))] border-t-transparent" />
            {t('common.loading')}
          </div>
        ) : agents.length === 0 ? (
          <div className="text-sm text-[rgb(var(--muted))]">{t('agents.noAgentsRegistered')}</div>
        ) : (
          <div className="space-y-2">
            {agents.map((agent) => (
              <AgentTile
                key={agent.agent_id}
                agent={agent}
                onAccept={(target) => acceptPairingMutation.mutate(target.agent_id)}
                onEdit={(target) => setEditTarget(target)}
                onDelete={(target) => {
                  setDeleteForce(false)
                  setDeleteTarget(target)
                }}
                onUpdate={(target) => openOtaModal(target)}
                onReboot={(target) => setRebootTarget(target)}
              />
            ))}
          </div>
        )}
      </section>

      {editTarget ? <AgentEditorDrawer key={editTarget.agent_id} agent={editTarget} onClose={() => setEditTarget(null)} /> : null}

      <Modal
        open={Boolean(deleteTarget)}
        title={t('common.delete')}
        onClose={() => {
          setDeleteTarget(null)
          setDeleteForce(false)
        }}
        footer={
          <div className="flex gap-2 justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                setDeleteTarget(null)
                setDeleteForce(false)
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button
              variant="danger"
              disabled={deleteAgentMutation.isPending || (deleteRequiresForce && !deleteForce)}
              onClick={() => {
                if (!deleteTarget) return
                deleteAgentMutation.mutate({
                  agentId: deleteTarget.agent_id,
                  force: deleteForce,
                })
              }}
            >
              {t('common.delete')}
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-[rgb(var(--muted))]">
            {deleteTarget ? `${deleteTarget.name || deleteTarget.agent_id} (${deleteTarget.agent_id})` : ''}
          </p>
          {deleteRequiresForce ? (
            <div className="space-y-2 rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-700">
              <div>{t('agents.deleteForceWarning')}</div>
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={deleteForce}
                  onChange={(event) => setDeleteForce(event.target.checked)}
                />
                <span>{t('agents.deleteForceLabel')}</span>
              </label>
            </div>
          ) : (
            <div className="space-y-2 rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3 text-sm">
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={deleteForce}
                  onChange={(event) => setDeleteForce(event.target.checked)}
                />
                <span>{t('agents.deleteForceOptionalInfo')}</span>
              </label>
            </div>
          )}
        </div>
      </Modal>

      <ConfirmDialog
        open={Boolean(rebootTarget)}
        title={t('agents.rebootAction')}
        body={rebootTarget ? `${rebootTarget.name || rebootTarget.agent_id} (${rebootTarget.agent_id})` : ''}
        confirmText={t('agents.rebootAction')}
        onCancel={() => setRebootTarget(null)}
        onConfirm={() => {
          if (!rebootTarget) return
          rebootMutation.mutate(rebootTarget.agent_id)
        }}
      />

      <Modal
        open={Boolean(otaTarget)}
        title={t('agents.updateAction')}
        onClose={() => {
          setOtaTarget(null)
          setOtaVersion('')
        }}
        footer={
          <div className="flex gap-2 justify-end">
            <Button
              variant="secondary"
              onClick={() => {
                setOtaTarget(null)
                setOtaVersion('')
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button
              disabled={!otaTarget || !otaVersion || otaMutation.isPending}
              onClick={() => {
                if (!otaTarget || !otaVersion) return
                otaMutation.mutate({ agentId: otaTarget.agent_id, version: otaVersion })
              }}
            >
              {t('agents.updateAction')}
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <div className="text-sm text-[rgb(var(--muted))]">{t('agents.updateSelectVersionHint')}</div>
          {installableFirmwareOptions.length === 0 ? (
            <div className="text-sm text-red-600">{t('agents.updateNoFirmware')}</div>
          ) : (
            <SelectField
              label={t('agents.updateVersionLabel')}
              value={otaVersion}
              onChange={(event) => setOtaVersion(event.target.value)}
            >
              {installableFirmwareOptions.map((entry) => (
                <option key={entry.version} value={entry.version}>
                  {entry.version}
                </option>
              ))}
            </SelectField>
          )}
        </div>
      </Modal>
    </div>
  )
}

function isOtaTimeoutError(error) {
  const details = error?.details
  const code = typeof details?.code === 'string' ? details.code.trim().toLowerCase() : ''
  return code === 'agent_timeout' || Number(error?.status) === 504
}
