import React, { useMemo, useState } from 'react'
import Icon from '@mdi/react'
import { mdiAutorenew } from '@mdi/js'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { Drawer } from '../../components/ui/Drawer.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { NumberField } from '../../components/ui/NumberField.jsx'
import { SelectField } from '../../components/ui/SelectField.jsx'
import { EntityEditHeader } from '../../components/ui/EntityEditHeader.jsx'
import { IconPicker } from '../../components/pickers/IconPicker.jsx'
import { otaCancelAgent, otaUpdateAgent, resetAgentInstallation, updateAgent, updateAgentRuntimeConfig } from '../../api/agentsApi.js'
import { getFirmwareCatalog } from '../../api/firmwareApi.js'
import { useToast } from '../../components/ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../../utils/apiErrorMapper.js'
import { DEFAULT_AGENT_ICON } from '../../icons/iconRegistry.js'
import { getAppConfig } from '../../utils/appConfig.js'
import { isInstallationInProgress, normalizeInstallationStatus } from './installationStatus.js'

export function AgentEditorDrawer({ agent, onClose }) {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)

  const [name, setName] = useState(typeof agent.name === 'string' ? agent.name : '')
  const [icon, setIcon] = useState(agent.icon ?? null)
  const [configurationUrl, setConfigurationUrl] = useState(typeof agent.configuration_url === 'string' ? agent.configuration_url : '')
  const initialRxPin = parsePinValue(agent?.runtime?.ir_rx_pin) ?? 34
  const initialTxPin = parsePinValue(agent?.runtime?.ir_tx_pin) ?? 4
  const [irRxPin, setIrRxPin] = useState(initialRxPin == null ? '' : String(initialRxPin))
  const [irTxPin, setIrTxPin] = useState(initialTxPin == null ? '' : String(initialTxPin))
  const [iconPickerOpen, setIconPickerOpen] = useState(false)
  const appConfig = getAppConfig()
  const runtime = agent?.runtime || {}
  const ota = agent?.ota || {}
  const installation = agent?.installation || {}
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

  const fillCurrentUrl = () => {
    if (typeof window === 'undefined') return
    const baseUrl = appConfig.publicBaseUrl.endsWith('/') ? appConfig.publicBaseUrl : `${appConfig.publicBaseUrl}/`
    const path = `${baseUrl}agent/${encodeURIComponent(agent.agent_id)}`
    const absoluteUrl = `${window.location.origin}${path}`
    setConfigurationUrl(absoluteUrl)
  }

  const saveMutation = useMutation({
    mutationFn: async () => {
      const metadataPayload = {
        name: name.trim() || null,
        icon: icon ?? null,
        configuration_url: configurationUrl.trim() || null,
      }
      const metadataChanged =
        metadataPayload.name !== (agent.name ?? null) ||
        metadataPayload.icon !== (agent.icon ?? null) ||
        metadataPayload.configuration_url !== (agent.configuration_url ?? null)

      if (metadataChanged) {
        await updateAgent(agent.agent_id, metadataPayload)
      }

      if (!isEsp32) {
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
      (icon ?? null) !== (agent.icon ?? null) ||
      (configurationUrl.trim() || null) !== (agent.configuration_url ?? null)
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

          <label className="block">
            <div className="mb-1 text-sm font-medium">{t('agents.configurationUrlLabel')}</div>
            <div className="relative">
              <input
                className="h-11 w-full rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] px-3 pr-12 text-sm text-[rgb(var(--fg))] outline-none focus:ring-2 focus:ring-[rgb(var(--primary))]"
                value={configurationUrl}
                onChange={(event) => setConfigurationUrl(event.target.value)}
              />
              <button
                type="button"
                aria-label={t('agents.configurationUrlAuto')}
                title={t('agents.configurationUrlAuto')}
                onClick={fillCurrentUrl}
                className="absolute right-3 top-1/2 -translate-y-1/2 rounded-md p-1 text-[rgb(var(--muted))] hover:text-[rgb(var(--fg))] focus:outline-none focus:ring-2 focus:ring-[rgb(var(--primary))] focus:ring-offset-2 focus:ring-offset-[rgb(var(--bg))]"
              >
                <Icon path={mdiAutorenew} size={0.8} />
              </button>
            </div>
            <div className="mt-1 text-xs text-[rgb(var(--muted))]">{t('agents.configurationUrlHint')}</div>
          </label>

          {isEsp32 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <NumberField
                label={t('agents.irRxPinLabel')}
                hint={t('agents.irRxPinHint')}
                min={0}
                max={39}
                step={1}
                value={irRxPin}
                aria-invalid={parsedRxPin == null}
                onChange={(event) => setIrRxPin(event.target.value)}
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
              />
            </div>
          ) : null}

          {otaSupported ? (
            <div className="rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3 space-y-3">
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
