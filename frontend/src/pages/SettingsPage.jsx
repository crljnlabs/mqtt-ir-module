import React, { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Card, CardBody, CardHeader, CardTitle } from '../components/ui/Card.jsx'
import { getAppConfig } from '../utils/appConfig.js'
import { getElectronicsStatus, getMqttStatus } from '../api/statusApi.js'
import { getSettings, updateSettings } from '../api/settingsApi.js'
import { getFirmwareCatalog } from '../api/firmwareApi.js'
import { Button } from '../components/ui/Button.jsx'
import { Modal } from '../components/ui/Modal.jsx'
import { NumberField } from '../components/ui/NumberField.jsx'
import { SelectField } from '../components/ui/SelectField.jsx'
import { TextField } from '../components/ui/TextField.jsx'
import { ErrorCallout } from '../components/ui/ErrorCallout.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../utils/apiErrorMapper.js'

export function SettingsPage() {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)
  const config = useMemo(() => getAppConfig(), [])
  const electronicsQuery = useQuery({ queryKey: ['status-electronics'], queryFn: getElectronicsStatus })
  const mqttStatusQuery = useQuery({ queryKey: ['status-mqtt'], queryFn: getMqttStatus, refetchInterval: 5000 })
  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: getSettings, staleTime: 60_000 })
  const firmwareQuery = useQuery({
    queryKey: ['firmware', 'esp32'],
    queryFn: () => getFirmwareCatalog('esp32'),
    staleTime: 60_000,
  })

  const irRxDevice = electronicsQuery.data?.ir_rx_device
  const irTxDevice = electronicsQuery.data?.ir_tx_device
  const deviceText = t('health.deviceLine', {
    rx: irRxDevice || t('common.notAvailable'),
    tx: irTxDevice || t('common.notAvailable'),
  })
  const debugLabel = electronicsQuery.data?.debug ? t('common.yes') : t('common.no')
  const writeKeyRequiredLabel = config.writeRequiresApiKey ? t('common.yes') : t('common.no')

  const [helpOpen, setHelpOpen] = useState(false)
  const [learningDirty, setLearningDirty] = useState(false)
  const [pressTakesDefault, setPressTakesDefault] = useState('')
  const [captureTimeoutMsDefault, setCaptureTimeoutMsDefault] = useState('')
  const [holdIdleTimeoutMs, setHoldIdleTimeoutMs] = useState('')
  const [aggregateRoundToUs, setAggregateRoundToUs] = useState('')
  const [aggregateMinMatchPercent, setAggregateMinMatchPercent] = useState('')
  const [mqttDirty, setMqttDirty] = useState(false)
  const [mqttHost, setMqttHost] = useState('')
  const [mqttPort, setMqttPort] = useState('1883')
  const [mqttUsername, setMqttUsername] = useState('')
  const [mqttPassword, setMqttPassword] = useState('')
  const [mqttInstance, setMqttInstance] = useState('')
  const [homeassistantEnabled, setHomeassistantEnabled] = useState(false)

  useEffect(() => {
    if (typeof window === 'undefined') return
    if (window.customElements?.get('esp-web-install-button')) return
    const scriptId = 'esp-web-tools-install-button'
    if (document.getElementById(scriptId)) return
    const script = document.createElement('script')
    script.id = scriptId
    script.type = 'module'
    script.src = 'https://unpkg.com/esp-web-tools/dist/web/install-button.js'
    document.head.appendChild(script)
  }, [])

  useEffect(() => {
    if (!settingsQuery.data || learningDirty) return
    const defaults = getLearningDefaults(settingsQuery.data)
    setPressTakesDefault(String(defaults.pressTakes))
    setCaptureTimeoutMsDefault(String(defaults.captureTimeoutMs))
    setHoldIdleTimeoutMs(String(defaults.holdIdleTimeoutMs))
    setAggregateRoundToUs(String(defaults.aggregateRoundToUs))
    setAggregateMinMatchPercent(String(defaults.aggregateMinMatchPercent))
  }, [settingsQuery.data, learningDirty])

  useEffect(() => {
    if (!settingsQuery.data || mqttDirty) return
    const defaults = getMqttDefaults(settingsQuery.data)
    setMqttHost(defaults.host)
    setMqttPort(String(defaults.port))
    setMqttUsername(defaults.username)
    setMqttInstance(defaults.instance)
    setMqttPassword('')
    setHomeassistantEnabled(Boolean(settingsQuery.data.homeassistant_enabled ?? false))
  }, [settingsQuery.data, mqttDirty])

  const updateMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      setLearningDirty(false)
      toast.show({ title: t('settings.learningTitle'), message: t('settings.learningSaved') })
    },
    onError: (e) => toast.show({ title: t('settings.learningTitle'), message: errorMapper.getMessage(e, 'settings.learningSaveFailed') }),
  })

  const mqttMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      queryClient.invalidateQueries({ queryKey: ['status-mqtt'] })
      setMqttDirty(false)
      setMqttPassword('')
      toast.show({ title: t('settings.mqttTitle'), message: t('settings.mqttSaved') })
    },
    onError: (e) => toast.show({ title: t('settings.mqttTitle'), message: errorMapper.getMessage(e, 'settings.mqttSaveFailed') }),
  })

  const learningDefaults = settingsQuery.data ? getLearningDefaults(settingsQuery.data) : null
  const mqttDefaults = settingsQuery.data ? getMqttDefaults(settingsQuery.data) : null

  const pressTakesValue = parseNumberInput(pressTakesDefault)
  const captureTimeoutValue = parseNumberInput(captureTimeoutMsDefault)
  const holdIdleValue = parseNumberInput(holdIdleTimeoutMs)
  const aggregateRoundValue = parseNumberInput(aggregateRoundToUs)
  const matchPercentValue = parseNumberInput(aggregateMinMatchPercent)
  const mqttPortValue = parseNumberInput(mqttPort)

  const mqttHostValue = normalizeText(mqttHost)
  const mqttUsernameValue = normalizeText(mqttUsername)
  const mqttInstanceValue = normalizeText(mqttInstance)
  const mqttPasswordValue = mqttPassword
  const homeassistantEnabledValue = Boolean(homeassistantEnabled)

  const isPressTakesValid = isNumberInRange(pressTakesValue, 1, 50)
  const isCaptureTimeoutValid = isNumberInRange(captureTimeoutValue, 100, 60000)
  const isHoldIdleValid = isNumberInRange(holdIdleValue, 50, 2000)
  const isAggregateRoundValid = isNumberInRange(aggregateRoundValue, 1, 1000)
  const isMatchPercentValid = isNumberInRange(matchPercentValue, 10, 100)
  const isMqttPortValid = isNumberInRange(mqttPortValue, 1, 65535)
  const isMqttInstanceValid = /^[A-Za-z0-9_-]*$/.test(mqttInstanceValue)
  const hasMqttPasswordInput = mqttPasswordValue.length > 0
  const hasMasterKey = Boolean(settingsQuery.data?.settings_master_key_configured)
  const hasMqttInvalid = !isMqttPortValid || !isMqttInstanceValid || (hasMqttPasswordInput && !hasMasterKey)

  const hasInvalid =
    !isPressTakesValid ||
    !isCaptureTimeoutValid ||
    !isHoldIdleValid ||
    !isAggregateRoundValid ||
    !isMatchPercentValid

  const hasChanges = Boolean(learningDefaults) && !hasInvalid && (
    pressTakesValue !== learningDefaults.pressTakes ||
    captureTimeoutValue !== learningDefaults.captureTimeoutMs ||
    holdIdleValue !== learningDefaults.holdIdleTimeoutMs ||
    aggregateRoundValue !== learningDefaults.aggregateRoundToUs ||
    matchPercentValue !== learningDefaults.aggregateMinMatchPercent
  )

  const hasMqttChanges = Boolean(mqttDefaults) && !hasMqttInvalid && (
    mqttHostValue !== mqttDefaults.host ||
    mqttPortValue !== mqttDefaults.port ||
    mqttUsernameValue !== mqttDefaults.username ||
    mqttInstanceValue !== mqttDefaults.instance ||
    homeassistantEnabledValue !== mqttDefaults.homeassistantEnabled ||
    hasMqttPasswordInput
  )

  const isSaving = updateMutation.isPending
  const isSavingMqtt = mqttMutation.isPending
  const disableLearningForm = !settingsQuery.data || isSaving
  const disableMqttForm = !settingsQuery.data || isSavingMqtt
  const mqttPasswordStored = Boolean(settingsQuery.data?.mqtt_password_set)
  const showMasterKeyWarning = !hasMasterKey
  const mqttConfigured = Boolean(mqttStatusQuery.data?.configured)
  const mqttConnected = Boolean(mqttStatusQuery.data?.connected)
  const mqttLastError = String(mqttStatusQuery.data?.last_error || '').trim()
  const hubIsAgentReadonlyValue = Boolean(settingsQuery.data?.hub_is_agent ?? true)
  const latestFirmwareVersion = String(firmwareQuery.data?.latest_installable_version || '').trim()
  const firmwareManifestUrl = `${config.apiBaseUrl}/firmware/webtools-manifest?agent_type=esp32`

  const handleLearningChange = (setter) => (event) => {
    setLearningDirty(true)
    setter(event.target.value)
  }

  const handleMqttChange = (setter) => (event) => {
    setMqttDirty(true)
    setter(event.target.value)
  }

  const handleSaveLearning = () => {
    if (!learningDefaults || hasInvalid || matchPercentValue == null) return
    updateMutation.mutate({
      press_takes_default: pressTakesValue,
      capture_timeout_ms_default: captureTimeoutValue,
      hold_idle_timeout_ms: holdIdleValue,
      aggregate_round_to_us: aggregateRoundValue,
      aggregate_min_match_ratio: Number((matchPercentValue / 100).toFixed(2)),
    })
  }

  const handleSaveMqtt = () => {
    if (!mqttDefaults || hasMqttInvalid || mqttPortValue == null) return
    const payload = {
      mqtt_host: mqttHostValue,
      mqtt_port: mqttPortValue,
      mqtt_username: mqttUsernameValue,
      mqtt_instance: mqttInstanceValue,
      homeassistant_enabled: homeassistantEnabledValue,
    }
    if (hasMqttPasswordInput) {
      payload.mqtt_password = mqttPasswordValue
    }
    mqttMutation.mutate(payload)
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{t('settings.runtime')}</CardTitle>
          <Button variant="secondary" size="sm" onClick={() => setHelpOpen(true)}>
            {t('settings.help')}
          </Button>
        </CardHeader>
        <CardBody>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-xs text-[rgb(var(--muted))]">{t('settings.baseUrl')}</div>
              <div className="font-semibold break-words">{config.publicBaseUrl}</div>
            </div>
            <div>
              <div className="text-xs text-[rgb(var(--muted))]">{t('settings.apiBaseUrl')}</div>
              <div className="font-semibold break-words">{config.apiBaseUrl}</div>
            </div>
            <div>
              <div className="text-xs text-[rgb(var(--muted))]">{t('health.device')}</div>
              <div className="font-semibold">{deviceText}</div>
            </div>
            <div>
              <div className="text-xs text-[rgb(var(--muted))]">{t('health.debug')}</div>
              <div className="font-semibold">{debugLabel}</div>
            </div>
            <div>
              <div className="text-xs text-[rgb(var(--muted))]">{t('settings.writeKeyRequired')}</div>
              <div className="font-semibold">{writeKeyRequiredLabel}</div>
            </div>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.agentTitle')}</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="text-sm text-[rgb(var(--muted))]">{t('settings.agentDescription')}</div>
          <div className="mt-3 max-w-sm">
            <TextField
              label={t('settings.hubIsAgentLabel')}
              hint={t('settings.hubIsAgentReadonlyHint')}
              value={hubIsAgentReadonlyValue ? t('common.yes') : t('common.no')}
              disabled
            />
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.esp32FlashTitle')}</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="text-sm text-[rgb(var(--muted))]">{t('settings.esp32FlashDescription')}</div>
          <div className="mt-2 text-sm">
            <span className="font-semibold">{t('settings.esp32LatestFirmwareLabel')}: </span>
            {latestFirmwareVersion ? latestFirmwareVersion : t('settings.esp32NoInstallableFirmware')}
          </div>
          {latestFirmwareVersion ? (
            <div className="mt-3">
              <esp-web-install-button manifest={firmwareManifestUrl}></esp-web-install-button>
            </div>
          ) : null}
          <div className="mt-2 text-xs text-[rgb(var(--muted))]">{t('settings.esp32FlashHint')}</div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.mqttTitle')}</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="text-sm text-[rgb(var(--muted))]">{t('settings.mqttDescription')}</div>
          <div className="mt-3 text-sm">
            <span className="font-semibold">{t('settings.mqttConnectionStatusLabel')}: </span>
            {mqttConfigured ? (
              mqttConnected ? (
                <span className="text-green-600">{t('settings.mqttConnected')}</span>
              ) : (
                <span className="text-red-600">{t('settings.mqttDisconnected')}</span>
              )
            ) : (
              <span className="text-[rgb(var(--muted))]">{t('settings.mqttNotConfigured')}</span>
            )}
          </div>
          {mqttLastError ? (
            <div className="mt-2 text-sm text-red-600">
              {t('settings.mqttLastErrorLabel')}: {mqttLastError}
            </div>
          ) : null}
          {showMasterKeyWarning ? (
            <div className="mt-3 rounded-xl border border-red-400/40 bg-red-500/10 px-3 py-2 text-sm text-red-700">
              {t('settings.mqttMasterKeyMissing')}
            </div>
          ) : null}
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <TextField
              label={t('settings.mqttHostLabel')}
              hint={t('settings.mqttHostHint')}
              value={mqttHost}
              disabled={disableMqttForm}
              onChange={handleMqttChange(setMqttHost)}
            />
            <NumberField
              label={t('settings.mqttPortLabel')}
              hint={t('settings.mqttPortHint')}
              value={mqttPort}
              min={1}
              max={65535}
              step={1}
              disabled={disableMqttForm}
              aria-invalid={!isMqttPortValid}
              onChange={handleMqttChange(setMqttPort)}
            />
            <TextField
              label={t('settings.mqttUsernameLabel')}
              hint={t('settings.mqttUsernameHint')}
              value={mqttUsername}
              disabled={disableMqttForm}
              onChange={handleMqttChange(setMqttUsername)}
            />
            <TextField
              type="password"
              label={t('settings.mqttPasswordLabel')}
              hint={mqttPasswordStored ? t('settings.mqttPasswordStoredHint') : t('settings.mqttPasswordHint')}
              value={mqttPassword}
              disabled={disableMqttForm}
              onChange={handleMqttChange(setMqttPassword)}
            />
            <SelectField
              label={t('settings.homeassistantEnabledLabel')}
              hint={t('settings.homeassistantEnabledHint')}
              value={homeassistantEnabled ? 'true' : 'false'}
              disabled={disableMqttForm}
              onChange={(event) => {
                setMqttDirty(true)
                setHomeassistantEnabled(event.target.value === 'true')
              }}
            >
              <option value="true">{t('common.yes')}</option>
              <option value="false">{t('common.no')}</option>
            </SelectField>
            <TextField
              label={t('settings.mqttBaseTopicLabel')}
              hint={t('settings.mqttBaseTopicHint')}
              value={mqttInstance}
              disabled={disableMqttForm}
              aria-invalid={!isMqttInstanceValid}
              onChange={handleMqttChange(setMqttInstance)}
            />
          </div>
          <div className="mt-4 flex justify-end">
            <Button onClick={handleSaveMqtt} disabled={disableMqttForm || hasMqttInvalid || !hasMqttChanges}>
              {t('common.save')}
            </Button>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t('settings.learningTitle')}</CardTitle>
        </CardHeader>
        <CardBody>
          <div className="text-sm text-[rgb(var(--muted))]">{t('settings.learningDescription')}</div>
          {settingsQuery.isError ? (
            <div className="mt-3">
              <ErrorCallout error={settingsQuery.error} />
            </div>
          ) : null}
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <NumberField
              label={t('settings.learningPressTakesLabel')}
              hint={t('settings.learningPressTakesHint')}
              value={pressTakesDefault}
              min={1}
              max={50}
              step={1}
              disabled={disableLearningForm}
              aria-invalid={!isPressTakesValid}
              onChange={handleLearningChange(setPressTakesDefault)}
            />
            <NumberField
              label={t('settings.learningTimeoutLabel')}
              hint={t('settings.learningTimeoutHint')}
              value={captureTimeoutMsDefault}
              min={100}
              max={60000}
              step={100}
              disabled={disableLearningForm}
              aria-invalid={!isCaptureTimeoutValid}
              onChange={handleLearningChange(setCaptureTimeoutMsDefault)}
            />
            <NumberField
              label={t('settings.learningHoldIdleLabel')}
              hint={t('settings.learningHoldIdleHint')}
              value={holdIdleTimeoutMs}
              min={50}
              max={2000}
              step={50}
              disabled={disableLearningForm}
              aria-invalid={!isHoldIdleValid}
              onChange={handleLearningChange(setHoldIdleTimeoutMs)}
            />
            <NumberField
              label={t('settings.learningRoundLabel')}
              hint={t('settings.learningRoundHint')}
              value={aggregateRoundToUs}
              min={1}
              max={1000}
              step={1}
              disabled={disableLearningForm}
              aria-invalid={!isAggregateRoundValid}
              onChange={handleLearningChange(setAggregateRoundToUs)}
            />
            <NumberField
              label={t('settings.learningMatchLabel')}
              hint={t('settings.learningMatchHint')}
              value={aggregateMinMatchPercent}
              min={10}
              max={100}
              step={1}
              disabled={disableLearningForm}
              aria-invalid={!isMatchPercentValid}
              onChange={handleLearningChange(setAggregateMinMatchPercent)}
            />
          </div>
          <div className="mt-4 flex justify-end">
            <Button onClick={handleSaveLearning} disabled={disableLearningForm || hasInvalid || !hasChanges}>
              {t('common.save')}
            </Button>
          </div>
        </CardBody>
      </Card>

      <Modal
        open={helpOpen}
        title={t('settings.help')}
        onClose={() => setHelpOpen(false)}
        footer={
          <div className="flex justify-end">
            <Button variant="secondary" onClick={() => setHelpOpen(false)}>
              {t('common.close')}
            </Button>
          </div>
        }
      >
        <div className="space-y-2 text-sm text-[rgb(var(--muted))]">
          <div>
            <div className="font-semibold text-[rgb(var(--fg))]">{t('settings.helpPublicBaseUrlTitle')}</div>
            <div>{t('settings.helpPublicBaseUrlBody')}</div>
          </div>
          <div>
            <div className="font-semibold text-[rgb(var(--fg))]">{t('settings.helpApiKeyTitle')}</div>
            <div>{t('settings.helpApiKeyBody')}</div>
          </div>
          <div>
            <div className="font-semibold text-[rgb(var(--fg))]">{t('settings.helpReverseProxyTitle')}</div>
            <div>{t('settings.helpReverseProxyBody')}</div>
          </div>
        </div>
      </Modal>
    </div>
  )
}

function getLearningDefaults(settings) {
  // Normalize learning defaults for the UI form state.
  return {
    pressTakes: getSettingNumber(settings?.press_takes_default, 5),
    captureTimeoutMs: getSettingNumber(settings?.capture_timeout_ms_default, 3000),
    holdIdleTimeoutMs: getSettingNumber(settings?.hold_idle_timeout_ms, 300),
    aggregateRoundToUs: getSettingNumber(settings?.aggregate_round_to_us, 10),
    aggregateMinMatchPercent: Math.round(getSettingNumber(settings?.aggregate_min_match_ratio, 0.6) * 100),
  }
}

function getMqttDefaults(settings) {
  // Normalize MQTT settings for the UI form state.
  return {
    host: normalizeText(settings?.mqtt_host),
    port: getSettingNumber(settings?.mqtt_port, 1883),
    username: normalizeText(settings?.mqtt_username),
    instance: normalizeText(settings?.mqtt_instance),
    homeassistantEnabled: Boolean(settings?.homeassistant_enabled ?? false),
  }
}

function getSettingNumber(value, fallback) {
  // Keep defaults stable when settings are missing or invalid.
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function normalizeText(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function parseNumberInput(value) {
  // Accept both empty and numeric inputs from number fields.
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : null
}

function isNumberInRange(value, min, max) {
  // Guard against invalid inputs before saving.
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
}
