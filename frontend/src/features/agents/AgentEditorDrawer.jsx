import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Drawer } from '../../components/ui/Drawer.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { NumberField } from '../../components/ui/NumberField.jsx'
import { SelectField } from '../../components/ui/SelectField.jsx'
import { EntityEditHeader } from '../../components/ui/EntityEditHeader.jsx'
import { IconPicker } from '../../components/pickers/IconPicker.jsx'
import { Tooltip } from '../../components/ui/Tooltip.jsx'
import { cn } from '../../components/ui/cn.js'
import { otaCancelAgent, otaUpdateAgent, resetAgentInstallation, updateAgent, updateAgentRuntimeConfig } from '../../api/agentsApi.js'
import { getFirmwareCatalog } from '../../api/firmwareApi.js'
import { useToast } from '../../components/ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../../utils/apiErrorMapper.js'
import { DEFAULT_AGENT_ICON } from '../../icons/iconRegistry.js'
import { isInstallationInProgress, normalizeInstallationStatus } from './installationStatus.js'

export function AgentEditorDrawer({ agent, onClose }) {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)

  const [name, setName] = useState(typeof agent.name === 'string' ? agent.name : '')
  const [icon, setIcon] = useState(agent.icon ?? null)
  const initialRxPin = parsePinValue(agent?.runtime?.ir_rx_pin) ?? 34
  const initialTxPin = parsePinValue(agent?.runtime?.ir_tx_pin) ?? 4
  const [irRxPin, setIrRxPin] = useState(initialRxPin == null ? '' : String(initialRxPin))
  const [irTxPin, setIrTxPin] = useState(initialTxPin == null ? '' : String(initialTxPin))
  const [iconPickerOpen, setIconPickerOpen] = useState(false)
  const runtime = agent?.runtime || {}
  const ota = agent?.ota || {}
  const installation = agent?.installation || {}
  const isOnline = String(agent.status || '').trim().toLowerCase() === 'online'
  const isEsp32 = String(runtime.agent_type || '').trim().toLowerCase() === 'esp32' && String(agent?.transport || '').trim().toLowerCase() === 'mqtt'
  const otaSupported = isEsp32 && Boolean(runtime.ota_supported || ota.supported)
  const installationInProgress = isInstallationInProgress(installation)
  const installationStatus = normalizeInstallationStatus(installation)
  const hasInstallationState = installationStatus !== 'idle'
  const parsedRxPin = parsePinInput(irRxPin)
  const parsedTxPin = parsePinInput(irTxPin)
  const pinsValid = !isEsp32 || (parsedRxPin != null && parsedTxPin != null)
  const [otaVersionOverride, setOtaVersionOverride] = useState('')

  const firmwareQuery = useQuery({
    queryKey: ['firmware', 'esp32'],
    queryFn: () => getFirmwareCatalog('esp32'),
    enabled: otaSupported,
    staleTime: 60_000,
  })

  const installableFirmwareOptions = useMemo(() => {
    const entries = firmwareQuery.data?.items || []
    return entries.filter((item) => Boolean(item.installable && item.ota_exists))
  }, [firmwareQuery.data])

  const installableVersions = useMemo(() => (
    installableFirmwareOptions
      .map((entry) => String(entry.version || '').trim())
      .filter((version) => Boolean(version))
  ), [installableFirmwareOptions])
  const latestInstallableVersion = String(firmwareQuery.data?.latest_installable_version || '').trim()
  const currentVersion = String(runtime.sw_version || agent?.sw_version || ota.current_version || '').trim()

  const preferredOtaVersion = useMemo(() => {
    if (!otaSupported || installableVersions.length === 0) {
      return ''
    }
    if (currentVersion && installableVersions.includes(currentVersion)) {
      return currentVersion
    }
    if (latestInstallableVersion && installableVersions.includes(latestInstallableVersion)) {
      return latestInstallableVersion
    }
    return installableVersions[0]
  }, [otaSupported, installableVersions, currentVersion, latestInstallableVersion])

  const otaVersion = useMemo(() => {
    if (otaVersionOverride && installableVersions.includes(otaVersionOverride)) {
      return otaVersionOverride
    }
    return preferredOtaVersion
  }, [otaVersionOverride, installableVersions, preferredOtaVersion])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const metadataPayload = {
        name: name.trim() || null,
        icon: icon ?? null,
      }
      const metadataChanged =
        metadataPayload.name !== (agent.name ?? null) ||
        metadataPayload.icon !== (agent.icon ?? null)

      if (metadataChanged) {
        await updateAgent(agent.agent_id, metadataPayload)
      }

      if (!isEsp32 || !isOnline) {
        return { pinsChanged: false }
      }

      if (parsedRxPin == null || parsedTxPin == null) {
        throw new Error('Invalid pin configuration')
      }
      const pinsChanged = parsedRxPin !== initialRxPin || parsedTxPin !== initialTxPin
      if (!pinsChanged) {
        return { pinsChanged: false }
      }

      await updateAgentRuntimeConfig(agent.agent_id, {
        ir_rx_pin: parsedRxPin,
        ir_tx_pin: parsedTxPin,
      })
      return { pinsChanged: true }
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agent', agent.agent_id] })
      if (result?.pinsChanged) {
        toast.show({ title: t('agents.pageTitle'), message: t('agents.savedWithRuntimeHint') })
      }
      onClose()
    },
    onError: (error) => {
      toast.show({ title: t('agents.pageTitle'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  function handleClose() {
    if (saveMutation.isPending) return
    const metadataChanged =
      (name.trim() || null) !== (agent.name ?? null) ||
      (icon ?? null) !== (agent.icon ?? null)
    const pinsChanged = isEsp32 && (parsedRxPin !== initialRxPin || parsedTxPin !== initialTxPin)
    if (metadataChanged || pinsChanged) {
      saveMutation.mutate()
      return
    }
    onClose()
  }

  const otaMutation = useMutation({
    mutationFn: (version) => otaUpdateAgent(agent.agent_id, { version }),
    onMutate: () => {
      toast.show({ title: t('agents.updateAction'), message: t('agents.updateRequested') })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agent', agent.agent_id] })
    },
    onError: (error) => {
      if (isOtaTimeoutError(error)) {
        queryClient.invalidateQueries({ queryKey: ['agents'] })
        queryClient.invalidateQueries({ queryKey: ['agent', agent.agent_id] })
        toast.show({ title: t('agents.updateAction'), message: t('agents.updateTimeoutHint') })
        return
      }
      toast.show({ title: t('agents.updateAction'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const otaCancelMutation = useMutation({
    mutationFn: () => otaCancelAgent(agent.agent_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agent', agent.agent_id] })
      toast.show({ title: t('agents.updateCancelAction'), message: t('agents.updateCancelRequested') })
    },
    onError: (error) => {
      toast.show({ title: t('agents.updateCancelAction'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  const resetInstallationMutation = useMutation({
    mutationFn: () => resetAgentInstallation(agent.agent_id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents'] })
      queryClient.invalidateQueries({ queryKey: ['agent', agent.agent_id] })
      toast.show({ title: t('agents.updateResetAction'), message: t('agents.updateResetDone') })
    },
    onError: (error) => {
      toast.show({ title: t('agents.updateResetAction'), message: errorMapper.getMessage(error, 'common.failed') })
    },
  })

  if (!agent) return null

  return (
    <>
      <Drawer
        open
        title={`${t('common.edit')} ${t('agents.pageTitle')}`}
        onClose={handleClose}
      >
        <div className="space-y-4">
          <EntityEditHeader
            label={t('agents.nameLabel')}
            name={name}
            onNameChange={(event) => setName(event.target.value)}
            onIconClick={() => setIconPickerOpen(true)}
          />

          {isEsp32 ? (
            <Tooltip wrapperClassName="block" label={!isOnline ? t('agents.onlyWhenOnline') : undefined}>
              <div className={!isOnline ? 'cursor-not-allowed' : undefined}>
                <div className={cn('grid grid-cols-1 md:grid-cols-2 gap-3', !isOnline && 'opacity-50 pointer-events-none')}>
                  <NumberField
                    label={t('agents.irRxPinLabel')}
                    hint={t('agents.irRxPinHint')}
                    min={0}
                    max={39}
                    step={1}
                    value={irRxPin}
                    aria-invalid={parsedRxPin == null}
                    onChange={(event) => setIrRxPin(event.target.value)}
                    disabled={!isOnline}
                  />
                  <NumberField
                    label={t('agents.irTxPinLabel')}
                    hint={t('agents.irTxPinHint')}
                    min={0}
                    max={39}
                    step={1}
                    value={irTxPin}
                    aria-invalid={parsedTxPin == null}
                    onChange={(event) => setIrTxPin(event.target.value)}
                    disabled={!isOnline}
                  />
                </div>
              </div>
            </Tooltip>
          ) : null}

          {otaSupported ? (
            <Tooltip wrapperClassName="block" label={!isOnline ? t('agents.onlyWhenOnline') : undefined}>
              <div className={!isOnline ? 'cursor-not-allowed' : undefined}>
                <div className={cn('rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3 space-y-3', !isOnline && 'opacity-50 pointer-events-none')}>
                  <div className="text-sm font-semibold">{t('agents.updateAction')}</div>
                  <div className="text-sm text-[rgb(var(--muted))]">{t('agents.updateSelectVersionHint')}</div>
                  {firmwareQuery.isLoading ? <div className="text-sm text-[rgb(var(--muted))]">{t('common.loading')}</div> : null}
                  {firmwareQuery.isError ? (
                    <div className="text-sm text-red-600">{errorMapper.getMessage(firmwareQuery.error, 'common.failed')}</div>
                  ) : null}
                  {hasInstallationState ? (
                    <div className="text-sm text-[rgb(var(--muted))]">
                      {installation.message || installationStatus.toUpperCase()}
                    </div>
                  ) : null}
                  {!firmwareQuery.isLoading && !firmwareQuery.isError && installableFirmwareOptions.length === 0 ? (
                    <div className="text-sm text-red-600">{t('agents.updateNoFirmware')}</div>
                  ) : null}
                  {!installationInProgress && !firmwareQuery.isLoading && !firmwareQuery.isError && installableFirmwareOptions.length > 0 ? (
                    <div className="space-y-3">
                      <SelectField
                        label={t('agents.updateVersionLabel')}
                        value={otaVersion}
                        onChange={(event) => setOtaVersionOverride(event.target.value)}
                        disabled={otaMutation.isPending || otaCancelMutation.isPending || resetInstallationMutation.isPending}
                      >
                        {installableFirmwareOptions.map((entry) => (
                          <option key={entry.version} value={entry.version}>
                            {entry.version}
                          </option>
                        ))}
                      </SelectField>
                      <div className="flex justify-end">
                        <Button
                          size="sm"
                          disabled={
                            !otaVersion ||
                            saveMutation.isPending ||
                            otaMutation.isPending ||
                            otaCancelMutation.isPending ||
                            resetInstallationMutation.isPending
                          }
                          onClick={() => otaMutation.mutate(otaVersion)}
                        >
                          {t('agents.updateAction')}
                        </Button>
                      </div>
                    </div>
                  ) : null}
                  {installationInProgress ? (
                    <div className="flex justify-end">
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={saveMutation.isPending || otaMutation.isPending || otaCancelMutation.isPending || resetInstallationMutation.isPending}
                        onClick={() => otaCancelMutation.mutate()}
                      >
                        {t('agents.updateCancelAction')}
                      </Button>
                    </div>
                  ) : null}
                  {hasInstallationState ? (
                    <div className="flex justify-end">
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={saveMutation.isPending || otaMutation.isPending || otaCancelMutation.isPending || resetInstallationMutation.isPending}
                        onClick={() => resetInstallationMutation.mutate()}
                      >
                        {t('agents.updateResetAction')}
                      </Button>
                    </div>
                  ) : null}
                </div>
              </div>
            </Tooltip>
          ) : null}

        </div>
      </Drawer>

      <IconPicker
        open={iconPickerOpen}
        title={t('common.icon')}
        initialIconKey={icon || DEFAULT_AGENT_ICON}
        onClose={() => setIconPickerOpen(false)}
        onBack={() => setIconPickerOpen(false)}
        onSelect={(key) => {
          setIcon(key)
          setIconPickerOpen(false)
        }}
      />
    </>
  )
}

function parsePinValue(value) {
  const parsed = Number(value)
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 39) return null
  return parsed
}

function parsePinInput(value) {
  const text = String(value || '').trim()
  if (!text) return null
  const parsed = Number(text)
  if (!Number.isInteger(parsed) || parsed < 0 || parsed > 39) return null
  return parsed
}

function isOtaTimeoutError(error) {
  const details = error?.details
  const code = typeof details?.code === 'string' ? details.code.trim().toLowerCase() : ''
  return code === 'agent_timeout' || Number(error?.status) === 504
}
