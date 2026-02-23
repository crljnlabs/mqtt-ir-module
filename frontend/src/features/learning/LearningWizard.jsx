import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Drawer } from '../../components/ui/Drawer.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { TextField } from '../../components/ui/TextField.jsx'
import { NumberField } from '../../components/ui/NumberField.jsx'
import { Collapse } from '../../components/ui/Collapse.jsx'
import { Badge } from '../../components/ui/Badge.jsx'
import { ErrorCallout } from '../../components/ui/ErrorCallout.jsx'
import { useToast } from '../../components/ui/ToastProvider.jsx'
import { startLearning, stopLearning, capturePress, captureHold, getLearningSessionStatus } from '../../api/learningApi.js'
import { createLearningStatusSocket } from '../../api/learningStatusSocket.js'
import { getLearningStatus } from '../../api/statusApi.js'
import { ApiErrorMapper } from '../../utils/apiErrorMapper.js'

export function LearningWizard({
  open,
  remoteId,
  remoteName,
  startExtend,
  targetButton,
  existingButtons,
  onClose,
  onAgentRequired,
}) {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)

  // Wizard flow state for press -> hold -> summary.
  const [step, setStep] = useState('press') // press -> hold -> next -> summary
  const [buttonName, setButtonName] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)

  // Capture configuration for press/hold.
  const [takes, setTakes] = useState(5)
  const [timeoutMs, setTimeoutMs] = useState(3000)

  // Local capture progress and status pushed over WebSocket.
  const [captured, setCaptured] = useState([]) // { name, press, hold }
  const [activeButtonName, setActiveButtonName] = useState(null)
  const [activeButtonId, setActiveButtonId] = useState(null)
  const [learnStatus, setLearnStatus] = useState({ learn_enabled: false, logs: [] })
  const [qualityLogStartIndex, setQualityLogStartIndex] = useState(0)
  // Track timeouts locally because timeout errors are not logged in the status stream.
  const [captureTimeout, setCaptureTimeout] = useState({ mode: null, take: null })

  const logContainerRef = useRef(null)
  const currentCaptureRef = useRef(null)

  // Keep a polling fallback so status stays usable even if WebSocket events are missed.
  const learningStatusQuery = useQuery({
    queryKey: ['status-learning'],
    queryFn: getLearningStatus,
    enabled: open,
    refetchInterval: open ? 2000 : false,
  })
  const learningSessionStatusQuery = useQuery({
    queryKey: ['learn-status'],
    queryFn: getLearningSessionStatus,
    enabled: open,
    refetchInterval: open ? 2000 : false,
  })
  const learningStatus = learningStatusQuery.data || null
  const learningSessionStatus = learningSessionStatusQuery.data || null
  const liveLearningActive = Boolean(learnStatus?.learn_enabled)
  const liveLearningRemoteId = learnStatus?.remote_id ?? null
  const polledSessionActive = Boolean(learningSessionStatus?.learn_enabled)
  const polledSessionRemoteId = learningSessionStatus?.remote_id ?? null
  const fallbackLearningActive = Boolean(learningStatus?.learn_enabled)
  const fallbackLearningRemoteId = learningStatus?.learn_remote_id ?? null
  const learningActive = liveLearningActive || polledSessionActive || fallbackLearningActive
  const learningRemoteId = liveLearningRemoteId ?? polledSessionRemoteId ?? fallbackLearningRemoteId
  const isCurrentRemoteLearning = learningActive && isSameRemote(learningRemoteId, remoteId)

  // Derive log list and key for scroll-to-latest behavior.
  const statusLogs = useMemo(() => {
    const liveLogs = Array.isArray(learnStatus.logs) ? learnStatus.logs : []
    const polledLogs = Array.isArray(learningSessionStatus?.logs) ? learningSessionStatus.logs : []
    return polledLogs.length > liveLogs.length ? polledLogs : liveLogs
  }, [learnStatus.logs, learningSessionStatus?.logs])
  const latestLogKey = statusLogs.length
    ? `${statusLogs[statusLogs.length - 1].timestamp}_${statusLogs[statusLogs.length - 1].level}_${statusLogs[statusLogs.length - 1].message}`
    : ''
  const currentCapture = useMemo(() => getCurrentCapture(statusLogs), [statusLogs])
  const pressTimeoutTake = captureTimeout.mode === 'press' ? captureTimeout.take : null
  const pressTakeStates = useMemo(() => {
    if (!currentCapture || currentCapture.mode !== 'press') return []
    return buildPressTakeStates(currentCapture, pressTimeoutTake)
  }, [currentCapture, pressTimeoutTake])
  const qualityScores = useMemo(
    () => getQualityScores(statusLogs, activeButtonId, qualityLogStartIndex),
    [statusLogs, activeButtonId, qualityLogStartIndex],
  )
  const qualityRows = useMemo(() => buildQualityRows(qualityScores), [qualityScores])
  const qualityHasAdvice = useMemo(() => qualityRows.some((row) => row.showAdvice), [qualityRows])
  const mutedSuccessStyle = { backgroundColor: 'rgb(var(--success) / 0.7)' }

  useEffect(() => {
    // Keep the latest capture snapshot accessible inside mutation callbacks.
    currentCaptureRef.current = currentCapture
  }, [currentCapture])

  // Mutations coordinate server-side learning actions with consistent error handling.
  const startMutation = useMutation({
    mutationFn: async () => {
      let latestLearningStatus = null
      try {
        latestLearningStatus = await queryClient.fetchQuery({
          queryKey: ['status-learning'],
          queryFn: getLearningStatus,
        })
      } catch {
        latestLearningStatus = queryClient.getQueryData(['status-learning'])
      }
      const latestLearningActive = Boolean(latestLearningStatus?.learn_enabled)
      const latestLearningRemoteId = latestLearningStatus?.learn_remote_id ?? null
      const latestLearningRemoteName = latestLearningStatus?.learn_remote_name ?? null

      if (latestLearningActive && latestLearningRemoteId && !isSameRemote(latestLearningRemoteId, remoteId)) {
        const remoteLabel = latestLearningRemoteName || latestLearningRemoteId
        throw new Error(t('wizard.errorLearningActiveOther', { remote: remoteLabel }))
      }
      if (latestLearningActive && isSameRemote(latestLearningRemoteId, remoteId)) {
        return {
          learn_enabled: true,
          remote_id: latestLearningRemoteId ?? toNumber(remoteId),
          remote_name: latestLearningRemoteName || remoteName || null,
          agent_id: latestLearningStatus?.learn_agent_id ?? latestLearningStatus?.agent_id ?? null,
          logs: Array.isArray(learnStatus?.logs) ? learnStatus.logs : [],
        }
      }
      return startLearning({ remoteId, extend: Boolean(startExtend) })
    },
    onSuccess: (data) => {
      const normalized = normalizeLearningStatusPayload(data, remoteId, remoteName)
      if (normalized.learn_enabled) {
        setLearnStatus(normalized)
      }
      queryClient.setQueryData(['learn-status'], normalized)
      queryClient.setQueryData(['status-learning'], toLearningStatusSummary(normalized))
      queryClient.invalidateQueries({ queryKey: ['status-learning'] })
      queryClient.invalidateQueries({ queryKey: ['learn-status'] })
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
    },
    onError: (error) => {
      const info = errorMapper.getErrorInfo(error)
      if (info.code === 'agent_required') {
        startMutation.reset()
        onAgentRequired?.(() => startMutation.mutate())
        return
      }
      toast.show({ title: t('wizard.title'), message: errorMapper.getMessage(error, 'wizard.errorStartFailed') })
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopLearning,
    onSuccess: () => {
      setLearnStatus({ learn_enabled: false, logs: [] })
      queryClient.setQueryData(['learn-status'], {
        learn_enabled: false,
        remote_id: null,
        remote_name: null,
        agent_id: null,
        logs: [],
      })
      queryClient.setQueryData(['status-learning'], {
        learn_enabled: false,
        learn_remote_id: null,
        learn_remote_name: null,
        learn_agent_id: null,
      })
      queryClient.invalidateQueries({ queryKey: ['status-learning'] })
      queryClient.invalidateQueries({ queryKey: ['learn-status'] })
    },
    onError: (e) => toast.show({ title: t('wizard.title'), message: errorMapper.getMessage(e, 'wizard.errorStopFailed') }),
  })

  const pressMutation = useMutation({
    mutationFn: async () => {
      const nameTrim = buttonName.trim()
      const nameForPress = targetButton?.name || (nameTrim ? nameTrim : null)

      const isExisting = Boolean(nameForPress && existingButtons.some((b) => b.name === nameForPress))
      const overwrite = Boolean(!startExtend || targetButton || (startExtend && isExisting))

      return capturePress({
        remoteId,
        takes: Number(takes),
        timeoutMs: Number(timeoutMs),
        overwrite,
        buttonName: nameForPress,
      })
    },
    onMutate: () => {
      setCaptureTimeout({ mode: null, take: null })
      setActiveButtonId(null)
      setQualityLogStartIndex(statusLogs.length)
      setLearnStatus((prev) => ensureLearningActive(prev, remoteId, remoteName))
    },
    onSuccess: (data) => {
      const name = data?.button?.name || buttonName.trim() || t('wizard.defaultButtonName')
      const buttonId = toNumber(data?.button?.id)
      setActiveButtonName(name)
      setActiveButtonId(buttonId > 0 ? buttonId : null)
      setCaptured((prev) => {
        const next = prev.filter((x) => x.name !== name)
        next.push({ name, press: true, hold: false })
        return next
      })
      setCaptureTimeout({ mode: null, take: null })
      queryClient.invalidateQueries({ queryKey: ['buttons', remoteId] })
      toast.show({ title: t('wizard.capturePress'), message: t('wizard.capturePressSuccess', { name }) })
      setStep('hold')
    },
    onError: (error) => {
      const info = errorMapper.getErrorInfo(error)
      if (info.code === 'agent_required') {
        pressMutation.reset()
        onAgentRequired?.(() => pressMutation.mutate())
        return
      }
      if (info.kind !== 'timeout') return
      const waitingTake = toNumber(currentCaptureRef.current?.waitingTake)
      setCaptureTimeout({ mode: 'press', take: waitingTake > 0 ? waitingTake : null })
    },
  })

  const holdMutation = useMutation({
    mutationFn: async () => {
      const name = activeButtonName || targetButton?.name
      if (!name) throw new Error(t('wizard.errorNoActiveButton'))

      const existing = existingButtons.find((b) => b.name === name) || null
      const overwrite = Boolean(!startExtend || targetButton || existing?.has_hold)

      return captureHold({
        remoteId,
        timeoutMs: Number(timeoutMs),
        overwrite,
        buttonName: name,
      })
    },
    onMutate: () => {
      setCaptureTimeout({ mode: null, take: null })
      setLearnStatus((prev) => ensureLearningActive(prev, remoteId, remoteName))
    },
    onSuccess: () => {
      const name = activeButtonName || targetButton?.name
      setCaptured((prev) => prev.map((x) => (x.name === name ? { ...x, hold: true } : x)))
      setCaptureTimeout({ mode: null, take: null })
      queryClient.invalidateQueries({ queryKey: ['buttons', remoteId] })
      toast.show({ title: t('wizard.captureHold'), message: t('wizard.captureHoldSuccess') })
      setStep('next')
    },
    onError: (error) => {
      const info = errorMapper.getErrorInfo(error)
      if (info.code === 'agent_required') {
        holdMutation.reset()
        onAgentRequired?.(() => holdMutation.mutate())
        return
      }
      if (info.kind !== 'timeout') return
      setCaptureTimeout({ mode: 'hold', take: null })
    },
  })

  useEffect(() => {
    if (!open) return
    // Reset wizard state and start a learning session when opening the drawer.
    startMutation.reset()
    pressMutation.reset()
    holdMutation.reset()
    const settingsSnapshot = queryClient.getQueryData(['settings'])
    const statusSnapshot = queryClient.getQueryData(['status-learning'])
    const sameRemoteActive = Boolean(statusSnapshot?.learn_enabled && isSameRemote(statusSnapshot?.learn_remote_id, remoteId))
    const defaultTakes = getSettingNumber(settingsSnapshot?.press_takes_default, 5)
    const defaultTimeoutMs = getSettingNumber(settingsSnapshot?.capture_timeout_ms_default, 3000)
    setCaptured([])
    setActiveButtonName(targetButton?.name || null)
    setActiveButtonId(null)
    setButtonName(targetButton?.name || '')
    setLearnStatus({
      learn_enabled: sameRemoteActive,
      remote_id: sameRemoteActive ? statusSnapshot?.learn_remote_id ?? toNumber(remoteId) : null,
      remote_name: sameRemoteActive ? statusSnapshot?.learn_remote_name || remoteName || null : null,
      logs: [],
    })
    setQualityLogStartIndex(0)
    setCaptureTimeout({ mode: null, take: null })
    setStep('press')
    setAdvancedOpen(false)
    setTakes(defaultTakes)
    setTimeoutMs(defaultTimeoutMs)
    void learningStatusQuery.refetch()
    void learningSessionStatusQuery.refetch()
    startMutation.mutate()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (open) return
    // Clear wizard state when the drawer closes to avoid stale data.
    startMutation.reset()
    pressMutation.reset()
    holdMutation.reset()
    setStep('press')
    setButtonName('')
    setAdvancedOpen(false)
    setTakes(5)
    setTimeoutMs(3000)
    setCaptured([])
    setActiveButtonName(null)
    setActiveButtonId(null)
    setLearnStatus({ learn_enabled: false, logs: [] })
    setQualityLogStartIndex(0)
    setCaptureTimeout({ mode: null, take: null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (!open) return
    // Keep status streaming resilient by reconnecting after transient socket failures.
    let isActive = true
    let socket = null
    let reconnectTimer = null
    let reconnectAttempts = 0

    const clearReconnectTimer = () => {
      if (reconnectTimer == null) return
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }

    const scheduleReconnect = () => {
      if (!isActive) return
      if (reconnectTimer != null) return
      const delayMs = Math.min(10000, 1000 * (2 ** reconnectAttempts))
      reconnectAttempts = Math.min(reconnectAttempts + 1, 6)
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null
        connect()
      }, delayMs)
    }

    const connect = () => {
      if (!isActive) return
      if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return
      socket = createLearningStatusSocket({
        onOpen: () => {
          reconnectAttempts = 0
        },
        onMessage: (payload) => {
          if (!isActive) return
          const normalized = normalizeLearningStatusPayload(payload)
          setLearnStatus(normalized)
          queryClient.setQueryData(['learn-status'], normalized)
          queryClient.setQueryData(['status-learning'], toLearningStatusSummary(normalized))
        },
        onClose: () => scheduleReconnect(),
        onError: () => scheduleReconnect(),
      })
    }

    const reconnectNow = () => {
      if (!isActive) return
      clearReconnectTimer()
      if (socket && socket.readyState === WebSocket.CONNECTING) return
      socket?.close()
      socket = null
      connect()
    }

    const handleOnline = () => reconnectNow()
    const handleVisibilityChange = () => {
      if (document.visibilityState !== 'visible') return
      if (socket && socket.readyState === WebSocket.OPEN) return
      reconnectNow()
    }

    connect()
    window.addEventListener('online', handleOnline)
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      isActive = false
      window.removeEventListener('online', handleOnline)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
      clearReconnectTimer()
      socket?.close()
    }
  }, [open, queryClient])

  // Keep logs pinned to the newest entry when new logs arrive.
  useEffect(() => {
    if (!open) return
    if (!latestLogKey) return
    if (!logContainerRef.current) return
    logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
  }, [open, latestLogKey])

  // Suggest the next auto-generated button name while learning.
  const defaultHint = useMemo(() => {
    const idx = learnStatus.next_button_index
    const prefix = t('wizard.defaultButtonPrefix')
    if (!idx) return `${prefix}_0001`
    return `${prefix}_${String(idx).padStart(4, '0')}`
  }, [learnStatus.next_button_index, t])

  const canClose = !isCurrentRemoteLearning

  // Use a single exit handler so closing the drawer stops learning when needed.
  const handleStopAndClose = async () => {
    if (!canClose) {
      await stopMutation.mutateAsync()
    }
    onClose()
  }

  return (
    <Drawer
      open={open}
      title={`${t('wizard.title')}: ${remoteName || `#${remoteId}`}`}
      onClose={handleStopAndClose}
      closeOnEscape={false}
    >
      <div className="space-y-4">
        {startMutation.isError ? <ErrorCallout error={startMutation.error} /> : null}

        <div className="rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3">
          <div className="text-sm font-semibold">{t('wizard.buttonSetup')}</div>
          <div className="mt-3">
            <TextField
              label={t('wizard.buttonName')}
              value={buttonName}
              onChange={(e) => setButtonName(e.target.value)}
              placeholder={defaultHint}
              hint={t('wizard.buttonNameHint')}
              disabled={Boolean(targetButton)}
            />
          </div>

          <div className="mt-3">
            <Collapse open={advancedOpen} onToggle={() => setAdvancedOpen((v) => !v)} title={t('common.advanced')}>
              <div className="grid grid-cols-1 gap-3">
                <NumberField
                  label={t('wizard.takesLabel')}
                  hint={t('wizard.takesHint')}
                  value={takes}
                  min={1}
                  max={50}
                  onChange={(e) => setTakes(e.target.value)}
                />
                <NumberField
                  label={t('wizard.timeoutLabel')}
                  hint={t('wizard.timeoutHint')}
                  value={timeoutMs}
                  min={100}
                  max={60000}
                  onChange={(e) => setTimeoutMs(e.target.value)}
                />
              </div>
            </Collapse>
          </div>
        </div>

        {step === 'press' ? (
          <div className="space-y-2">
            <Button className="w-full" onClick={() => pressMutation.mutate()} disabled={pressMutation.isPending || startMutation.isPending}>
              {t('wizard.capturePress')}
            </Button>
            {pressMutation.isError ? <ErrorCallout error={pressMutation.error} /> : null}
          </div>
        ) : null}

        {step === 'hold' ? (
          <div className="space-y-2">
            <Button className="w-full" onClick={() => holdMutation.mutate()} disabled={holdMutation.isPending || startMutation.isPending}>
              {t('wizard.captureHold')} ({t('common.optional')})
            </Button>
            <Button className="w-full" variant="secondary" onClick={() => setStep('next')}>
              {t('wizard.skip')}
            </Button>
            {holdMutation.isError ? <ErrorCallout error={holdMutation.error} /> : null}
          </div>
        ) : null}

        {step === 'next' ? (
          <div className="space-y-2">
            <Button className="w-full" onClick={() => resetForNextButton()}>
              {t('wizard.addAnother')}
            </Button>
            <Button
              className="w-full"
              variant="secondary"
              onClick={async () => {
                await stopMutation.mutateAsync()
                setStep('summary')
              }}
            >
              {t('wizard.finish')}
            </Button>
          </div>
        ) : null}

        {step === 'summary' ? (
          <div className="space-y-3">
            <div className="font-semibold">{t('wizard.summary')}</div>
            <div className="space-y-2">
              {captured.map((x) => (
                <div key={x.name} className="rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3">
                  <div className="font-semibold text-sm">{x.name}</div>
                  <div className="text-xs text-[rgb(var(--muted))]">
                    {t('wizard.summaryPress')}: {x.press ? t('wizard.summaryOk') : t('wizard.summaryMissing')} • {t('wizard.summaryHold')}:{' '}
                    {x.hold ? t('wizard.summaryOk') : t('wizard.summaryMissing')}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {step !== 'summary' ? (
          <div className="rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3">
            <div className="flex items-center justify-between">
              <div className="font-semibold text-sm">{t('wizard.statusTitle')}</div>
            </div>

            {isCurrentRemoteLearning ? null : (
              <div className="mt-2 text-xs text-[rgb(var(--muted))]">{t('wizard.statusInactive')}</div>
            )}

            {currentCapture ? (
              <div className="mt-3 rounded-lg border border-[rgb(var(--border))] bg-[rgb(var(--card))] p-2">
                <div className="text-xs font-semibold">{t('wizard.captureProgressTitle')}</div>
                <div className="mt-1 text-xs text-[rgb(var(--muted))]">
                  {currentCapture.mode === 'press' ? t('wizard.captureProgressPress') : t('wizard.captureProgressHold')}
                  {currentCapture.buttonName ? ` • ${currentCapture.buttonName}` : ''}
                </div>

                {currentCapture.mode === 'press' ? (
                  <div className="mt-2 grid gap-2">
                    {pressTakeStates.map((take) => (
                      <div key={take.index} className="flex items-center justify-between text-xs">
                        <div>{t('wizard.takeLabel', { index: take.index })}</div>
                        <Badge variant={take.variant} style={take.variant === 'success' ? mutedSuccessStyle : undefined} className="gap-1">
                          {take.status === 'captured' ? <CheckIcon /> : null}
                          {t(take.labelKey)}
                        </Badge>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="mt-2 flex items-center gap-2 text-xs">
                    <Badge
                      variant={
                        currentCapture.finished
                          ? 'success'
                          : captureTimeout.mode === 'hold'
                            ? 'danger'
                            : currentCapture.waiting
                              ? 'warning'
                              : 'neutral'
                      }
                      style={currentCapture.finished ? mutedSuccessStyle : undefined}
                      className="gap-1"
                    >
                      {currentCapture.finished ? <CheckIcon /> : null}
                      {currentCapture.finished
                        ? t('wizard.takeStatusCaptured')
                        : captureTimeout.mode === 'hold'
                          ? t('wizard.takeStatusTimeout')
                          : currentCapture.waiting
                            ? t('wizard.takeStatusWaiting')
                            : t('wizard.takeStatusPending')}
                    </Badge>
                  </div>
                )}
              </div>
            ) : null}

            {qualityRows.length ? (
              <div className="mt-3 rounded-lg border border-[rgb(var(--border))] bg-[rgb(var(--card))] p-2">
                <div className="text-xs font-semibold">{t('wizard.qualityTitle')}</div>
                <div className="mt-2 grid gap-2 text-xs">
                  {qualityRows.map((row) => (
                    <div key={row.key} className="flex items-center justify-between">
                      <div>{t(row.labelKey)}</div>
                      <div className="flex items-center gap-2">
                        <Badge variant={row.variant} style={row.variant === 'success' ? mutedSuccessStyle : undefined} className="gap-1">
                          {row.variant === 'success' ? <CheckIcon /> : null}
                          {t(row.qualityLabelKey)}
                        </Badge>
                        <span>{t('wizard.qualityScore', { score: formatQualityScore(row.score) })}</span>
                      </div>
                    </div>
                  ))}
                </div>
                {qualityHasAdvice ? (
                  <div className="mt-2 text-[11px] text-[rgb(var(--warning))]">
                    {t('wizard.qualityAdvice')}
                  </div>
                ) : null}
              </div>
            ) : null}

            {statusLogs.length ? (
              <div ref={logContainerRef} className="mt-3 max-h-40 overflow-auto space-y-2">
                {statusLogs.slice(-30).map((l, idx) => {
                  return (
                    <div key={`${l.timestamp}_${idx}`} className="text-[11px] text-[rgb(var(--muted))]">
                      {formatLogTime(l.timestamp)} [{l.level}] {l.message}
                    </div>
                  )
                })}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </Drawer>
  )

  function resetForNextButton() {
    setStep('press')
    setActiveButtonName(null)
    setActiveButtonId(null)
    setButtonName('')
    setAdvancedOpen(false)
    setQualityLogStartIndex(statusLogs.length)
    setCaptureTimeout({ mode: null, take: null })
  }
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      className="h-3 w-3"
      fill="currentColor"
    >
      <path d="M16.704 5.296a1 1 0 0 1 0 1.414l-7.5 7.5a1 1 0 0 1-1.414 0l-3.5-3.5a1 1 0 1 1 1.414-1.414l2.793 2.793 6.793-6.793a1 1 0 0 1 1.414 0z" />
    </svg>
  )
}

function formatLogTime(timestampSeconds) {
  // Convert epoch seconds to local HH:mm:ss to keep logs compact.
  if (!Number.isFinite(timestampSeconds)) return ''
  const date = new Date(timestampSeconds * 1000)
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  const seconds = String(date.getSeconds()).padStart(2, '0')
  return `${hours}:${minutes}:${seconds}`
}

function getCurrentCapture(logs) {
  // Inspect the latest capture-related log group to infer current capture state.
  if (!Array.isArray(logs) || !logs.length) return null

  const startIndex = findLastIndex(logs, (entry) =>
    entry?.message === 'Capture press started' || entry?.message === 'Capture hold started'
  )
  if (startIndex < 0) return null

  const startEntry = logs[startIndex]
  const slice = logs.slice(startIndex)

  if (startEntry.message === 'Capture press started') {
    const totalTakes = toNumber(startEntry?.data?.takes)
    const buttonName = toStringValue(startEntry?.data?.button_name)
    let waitingTake = null
    const capturedTakes = []
    let finished = false

    for (const entry of slice) {
      if (entry?.message === 'Waiting for IR press') {
        waitingTake = toNumber(entry?.data?.take)
      }
      if (entry?.message === 'Captured press take') {
        const takeNumber = toNumber(entry?.data?.take)
        if (takeNumber) capturedTakes.push(takeNumber)
      }
      if (entry?.message === 'Capture press finished') {
        finished = true
      }
    }

    return {
      mode: 'press',
      buttonName,
      totalTakes,
      waitingTake,
      capturedTakes,
      finished,
    }
  }

  if (startEntry.message === 'Capture hold started') {
    let finished = false
    let waiting = false
    for (const entry of slice) {
      if (entry?.message === 'Waiting for IR hold (initial frame)') {
        waiting = true
      }
      if (entry?.message === 'Capture hold finished') {
        finished = true
      }
    }
    return {
      mode: 'hold',
      buttonName: null,
      finished,
      waiting,
    }
  }

  return null
}

function buildPressTakeStates(capture, timeoutTake) {
  // Build per-take UI status from the most recent press capture logs plus timeout state.
  const totalTakes = Math.max(0, toNumber(capture.totalTakes))
  const capturedSet = new Set((capture.capturedTakes || []).filter(Boolean))
  const waitingTake = toNumber(capture.waitingTake)
  const timedOutTake = toNumber(timeoutTake)

  const states = []
  for (let i = 1; i <= totalTakes; i += 1) {
    let status = 'pending'
    if (capturedSet.has(i)) status = 'captured'
    else if (timedOutTake === i) status = 'timeout'
    else if (waitingTake === i) status = 'waiting'
    states.push({
      index: i,
      status,
      labelKey: status === 'captured'
        ? 'wizard.takeStatusCaptured'
        : status === 'timeout'
          ? 'wizard.takeStatusTimeout'
        : status === 'waiting'
          ? 'wizard.takeStatusWaiting'
          : 'wizard.takeStatusPending',
      variant: status === 'captured' ? 'success' : status === 'timeout' ? 'danger' : status === 'waiting' ? 'warning' : 'neutral',
    })
  }
  return states
}

function getQualityScores(logs, buttonId, startIndex) {
  // Extract the latest press/hold quality scores for the active button only.
  if (!Array.isArray(logs) || !logs.length) return { press: null, hold: null }
  const expectedButtonId = toNumber(buttonId)
  if (expectedButtonId <= 0) return { press: null, hold: null }
  const safeStart = Math.max(0, Math.min(logs.length, toNumber(startIndex)))
  const scopedLogs = logs.slice(safeStart)
  if (!scopedLogs.length) return { press: null, hold: null }

  let press = null
  let hold = null

  for (let i = scopedLogs.length - 1; i >= 0; i -= 1) {
    const entry = scopedLogs[i]
    const entryButtonId = toNumber(entry?.data?.button_id)
    if (entryButtonId !== expectedButtonId) continue
    if (!press && entry?.message === 'Capture press finished') {
      const rawScore = entry?.data?.quality
      if (rawScore != null) {
        const score = Number(rawScore)
        if (Number.isFinite(score)) press = { score }
      }
    }
    if (!hold && entry?.message === 'Capture hold finished') {
      const rawScore = entry?.data?.quality
      if (rawScore != null) {
        const score = Number(rawScore)
        if (Number.isFinite(score)) hold = { score }
      }
    }
    if (press && hold) break
  }

  return { press, hold }
}

function buildQualityRows(scores) {
  // Convert quality scores into UI rows for press/hold.
  if (!scores) return []
  const rows = []
  if (scores.press) {
    const row = buildQualityRow({ key: 'press', labelKey: 'wizard.qualityPress', score: scores.press.score })
    if (row) rows.push(row)
  }
  if (scores.hold) {
    const row = buildQualityRow({ key: 'hold', labelKey: 'wizard.qualityHold', score: scores.hold.score })
    if (row) rows.push(row)
  }
  return rows
}

function buildQualityRow({ key, labelKey, score }) {
  const summary = getQualitySummary(score)
  if (!summary) return null
  return {
    key,
    labelKey,
    score,
    qualityLabelKey: summary.qualityLabelKey,
    variant: summary.variant,
    showAdvice: summary.showAdvice,
  }
}

function getQualitySummary(score) {
  // Map the quality score to a badge style and optional guidance text.
  if (!Number.isFinite(score)) return null
  if (score >= 0.85) {
    return { qualityLabelKey: 'wizard.qualityGood', variant: 'success', showAdvice: false }
  }
  if (score >= 0.7) {
    return { qualityLabelKey: 'wizard.qualityOk', variant: 'warning', showAdvice: false }
  }
  return { qualityLabelKey: 'wizard.qualityLow', variant: 'danger', showAdvice: true }
}

function formatQualityScore(score) {
  // Keep a stable two-decimal quality display.
  if (!Number.isFinite(score)) return '0.00'
  return score.toFixed(2)
}

function toNumber(value) {
  // Normalize mixed data values into a usable number.
  if (typeof value === 'number' && Number.isFinite(value)) return value
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

function toStringValue(value) {
  // Normalize mixed data values into a display-safe string.
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number') return String(value)
  return ''
}

function getSettingNumber(value, fallback) {
  // Allow settings defaults to safely fall back when missing or invalid.
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

function findLastIndex(items, predicate) {
  // Provide findLastIndex support without requiring newer runtime helpers.
  for (let i = items.length - 1; i >= 0; i -= 1) {
    if (predicate(items[i], i)) return i
  }
  return -1
}

function normalizeLearningStatusPayload(payload, fallbackRemoteId = null, fallbackRemoteName = null) {
  if (!payload || typeof payload !== 'object') {
    return { learn_enabled: false, remote_id: null, remote_name: null, logs: [] }
  }
  const logs = Array.isArray(payload.logs) ? payload.logs : []
  const remoteId = payload.remote_id ?? payload.learn_remote_id ?? fallbackRemoteId
  const remoteName = payload.remote_name ?? payload.learn_remote_name ?? fallbackRemoteName
  const agentId = payload.agent_id ?? payload.learn_agent_id ?? null
  return {
    ...payload,
    learn_enabled: Boolean(payload.learn_enabled),
    remote_id: remoteId ?? null,
    remote_name: remoteName ?? null,
    agent_id: agentId ?? null,
    logs,
  }
}

function toLearningStatusSummary(payload) {
  const normalized = normalizeLearningStatusPayload(payload)
  if (!normalized.learn_enabled) {
    return { learn_enabled: false, learn_remote_id: null, learn_remote_name: null, learn_agent_id: null }
  }
  return {
    learn_enabled: true,
    learn_remote_id: normalized.remote_id ?? null,
    learn_remote_name: normalized.remote_name ?? null,
    learn_agent_id: normalized.agent_id ?? null,
  }
}

function ensureLearningActive(previous, remoteId, remoteName) {
  const normalized = normalizeLearningStatusPayload(previous, remoteId, remoteName)
  return {
    ...normalized,
    learn_enabled: true,
    remote_id: normalized.remote_id ?? toNumber(remoteId) ?? null,
    remote_name: normalized.remote_name || remoteName || null,
    logs: normalized.logs,
  }
}

function isSameRemote(left, right) {
  const leftValue = toNumber(left)
  const rightValue = toNumber(right)
  return leftValue > 0 && rightValue > 0 && leftValue === rightValue
}
