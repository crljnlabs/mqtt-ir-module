import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiChevronLeft, mdiRefresh } from '@mdi/js'

import { getAgent, getAgentDebug, getAgentLogs, setAgentDebug } from '../api/agentsApi.js'
import { createAgentLogsSocket } from '../api/agentLogsSocket.js'
import { Button } from '../components/ui/Button.jsx'
import { Card, CardBody, CardHeader, CardTitle } from '../components/ui/Card.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { TextField } from '../components/ui/TextField.jsx'
import { SelectField } from '../components/ui/SelectField.jsx'

const MAX_LOGS = 100
const LEVELS = ['debug', 'info', 'warn', 'error']
const LEVEL_BADGE_VARIANT = {
  debug: 'neutral',
  info: 'success',
  warn: 'warning',
  error: 'danger',
}
const TIME_RANGES = [
  { value: 'all', label: 'All time' },
  { value: '300', label: 'Last 5m' },
  { value: '900', label: 'Last 15m' },
  { value: '3600', label: 'Last 1h' },
]

export function AgentLogsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const { agentId = '' } = useParams()
  const queryClient = useQueryClient()

  const [liveLogsByAgent, setLiveLogsByAgent] = useState({})
  const [socketConnected, setSocketConnected] = useState(false)
  const [search, setSearch] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [timeRange, setTimeRange] = useState('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const [errorsOnly, setErrorsOnly] = useState(false)
  const [currentTs, setCurrentTs] = useState(0)
  const [enabledLevels, setEnabledLevels] = useState({
    debug: true,
    info: true,
    warn: true,
    error: true,
  })
  const reconnectTimerRef = useRef(null)
  const socketRef = useRef(null)
  const logContainerRef = useRef(null)

  const backTarget = useMemo(() => {
    const fromState = location.state?.from
    if (typeof fromState === 'string' && fromState.trim()) return fromState
    return `/agent/${agentId}`
  }, [location.state, agentId])

  const agentQuery = useQuery({
    queryKey: ['agent', agentId],
    queryFn: () => getAgent(agentId),
    enabled: Boolean(agentId),
  })
  const agentTransport = String(agentQuery.data?.transport || '').trim().toLowerCase()
  const debugQuery = useQuery({
    queryKey: ['agent-debug', agentId],
    queryFn: () => getAgentDebug(agentId),
    enabled: Boolean(agentId) && agentTransport === 'mqtt',
  })
  const debugMutation = useMutation({
    mutationFn: (enabled) => setAgentDebug(agentId, enabled),
    onSuccess: (payload) => {
      queryClient.setQueryData(['agent-debug', agentId], payload)
    },
  })
  const snapshotQuery = useQuery({
    queryKey: ['agent-logs', agentId],
    queryFn: () => getAgentLogs(agentId, MAX_LOGS),
    enabled: Boolean(agentId),
  })
  const snapshotLogs = useMemo(() => {
    const entries = Array.isArray(snapshotQuery.data?.items) ? snapshotQuery.data.items : []
    return entries.map((entry) => normalizeLogEntry(entry)).filter(Boolean)
  }, [snapshotQuery.data])

  useEffect(() => {
    if (!agentId) return undefined
    let cancelled = false

    const connect = () => {
      if (cancelled) return
      const socket = createAgentLogsSocket(agentId, {
        onOpen: () => setSocketConnected(true),
        onClose: () => {
          setSocketConnected(false)
          if (cancelled) return
          reconnectTimerRef.current = window.setTimeout(connect, 1500)
        },
        onError: () => {
          setSocketConnected(false)
        },
        onMessage: (payload) => {
          const normalized = normalizeLogEntry(payload)
          if (!normalized) return
          setLiveLogsByAgent((prev) => {
            const current = Array.isArray(prev[agentId]) ? prev[agentId] : []
            const next = [...current, normalized]
            if (next.length > MAX_LOGS) next.splice(0, next.length - MAX_LOGS)
            return { ...prev, [agentId]: next }
          })
        },
      })
      socketRef.current = socket
    }

    connect()
    return () => {
      cancelled = true
      setSocketConnected(false)
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
        reconnectTimerRef.current = null
      }
      if (socketRef.current) {
        socketRef.current.close()
        socketRef.current = null
      }
    }
  }, [agentId])

  useEffect(() => {
    if (timeRange === 'all') return undefined
    const timerId = window.setInterval(() => setCurrentTs(Date.now() / 1000), 1000)
    return () => window.clearInterval(timerId)
  }, [timeRange])

  const logs = useMemo(() => {
    const liveLogs = Array.isArray(liveLogsByAgent[agentId]) ? liveLogsByAgent[agentId] : []
    const merged = [...snapshotLogs, ...liveLogs]
    const deduped = []
    const seen = new Set()
    for (const entry of merged) {
      const key = [
        entry.ts,
        entry.level,
        entry.category,
        entry.message,
        entry.request_id || '',
        entry.error_code || '',
      ].join('|')
      if (seen.has(key)) continue
      seen.add(key)
      deduped.push(entry)
    }
    if (deduped.length <= MAX_LOGS) return deduped
    return deduped.slice(deduped.length - MAX_LOGS)
  }, [snapshotLogs, liveLogsByAgent, agentId])

  const categories = useMemo(() => {
    const values = new Set(['send', 'learn', 'pairing', 'runtime', 'transport', 'system'])
    for (const entry of logs) {
      const category = String(entry.category || '').trim()
      if (category) values.add(category)
    }
    return ['all', ...Array.from(values).sort((a, b) => a.localeCompare(b))]
  }, [logs])

  const filteredLogs = useMemo(() => {
    const query = search.trim().toLowerCase()
    const rangeSeconds = timeRange === 'all' ? null : Number(timeRange)
    return logs.filter((entry) => {
      if (!enabledLevels[entry.level]) return false
      if (errorsOnly && entry.level !== 'error') return false
      if (categoryFilter !== 'all' && entry.category !== categoryFilter) return false
      if (rangeSeconds && Number.isFinite(rangeSeconds) && currentTs > 0 && currentTs - entry.ts > rangeSeconds) return false
      if (!query) return true
      const haystack = [
        entry.message,
        entry.category,
        entry.error_code || '',
        entry.request_id || '',
        JSON.stringify(entry.meta || {}),
      ]
        .join(' ')
        .toLowerCase()
      return haystack.includes(query)
    })
  }, [logs, enabledLevels, errorsOnly, categoryFilter, timeRange, search, currentTs])

  useEffect(() => {
    if (!autoScroll) return
    const container = logContainerRef.current
    if (!container) return
    container.scrollTop = container.scrollHeight
  }, [autoScroll, filteredLogs.length])

  const toggleLevel = (level) => {
    setEnabledLevels((prev) => ({ ...prev, [level]: !prev[level] }))
  }

  const hasAgent = Boolean(agentQuery.data)
  if (agentQuery.isError || (!agentQuery.isLoading && !hasAgent)) {
    return (
      <Card>
        <CardBody className="space-y-3">
          <div className="text-sm text-[rgb(var(--muted))]">{t('errors.notFoundTitle')}</div>
          <div>
            <Button variant="secondary" onClick={() => navigate('/agents')}>
              {t('nav.agents')}
            </Button>
          </div>
        </CardBody>
      </Card>
    )
  }

  const agent = agentQuery.data || null
  const agentLabel = agent ? (agent.name || agent.agent_id) : agentId

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Button variant="ghost" size="sm" onClick={() => navigate(backTarget)}>
            <Icon path={mdiChevronLeft} size={0.9} />
            Back
          </Button>
          <div className="truncate font-semibold">Logs: {agentLabel}</div>
        </div>
        <div className="flex items-center gap-2">
          {agentTransport === 'mqtt' ? (
            <Button
              size="sm"
              variant={debugQuery.data?.debug ? 'primary' : 'secondary'}
              disabled={debugQuery.isLoading || debugMutation.isPending}
              onClick={() => debugMutation.mutate(!(debugQuery.data?.debug ?? false))}
            >
              Agent Debug: {debugQuery.data?.debug ? 'ON' : 'OFF'}
            </Button>
          ) : null}
          <Badge variant={socketConnected ? 'success' : 'warning'}>{socketConnected ? 'Live' : 'Reconnecting'}</Badge>
        </div>
      </div>

      <Card>
        <CardHeader className="items-start">
          <CardTitle>Filters</CardTitle>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => snapshotQuery.refetch()}
            disabled={snapshotQuery.isFetching}
          >
            <Icon path={mdiRefresh} size={0.8} />
            Refresh
          </Button>
        </CardHeader>
        <CardBody className="space-y-3">
          <TextField
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            onClear={() => setSearch('')}
            clearLabel={t('common.clear')}
            placeholder="Search message, category, request id..."
          />
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <SelectField
              label="Category"
              value={categoryFilter}
              onChange={(event) => setCategoryFilter(event.target.value)}
            >
              {categories.map((category) => (
                <option key={category} value={category}>
                  {category}
                </option>
              ))}
            </SelectField>
            <SelectField
              label="Time range"
              value={timeRange}
              onChange={(event) => setTimeRange(event.target.value)}
            >
              {TIME_RANGES.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </SelectField>
            <div className="flex flex-wrap gap-2 items-end">
              <Button
                variant={errorsOnly ? 'primary' : 'secondary'}
                size="sm"
                className="h-11"
                onClick={() => setErrorsOnly((prev) => !prev)}
              >
                Errors only
              </Button>
              <Button
                variant={autoScroll ? 'primary' : 'secondary'}
                size="sm"
                className="h-11"
                onClick={() => setAutoScroll((prev) => !prev)}
              >
                Auto-scroll
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            {LEVELS.map((level) => (
              <Button
                key={level}
                size="sm"
                variant={enabledLevels[level] ? 'primary' : 'secondary'}
                onClick={() => toggleLevel(level)}
              >
                {level.toUpperCase()}
              </Button>
            ))}
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Events ({filteredLogs.length})</CardTitle>
        </CardHeader>
        <CardBody>
          {snapshotQuery.isLoading ? (
            <div className="text-sm text-[rgb(var(--muted))]">{t('common.loading')}</div>
          ) : filteredLogs.length === 0 ? (
            <div className="text-sm text-[rgb(var(--muted))]">No log events in the selected range.</div>
          ) : (
            <div ref={logContainerRef} className="max-h-[60vh] overflow-auto space-y-2 pr-1">
              {filteredLogs.map((entry, index) => (
                <div
                  key={`${entry.ts}-${entry.level}-${entry.message}-${index}`}
                  className="rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3 space-y-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={LEVEL_BADGE_VARIANT[entry.level] || 'neutral'}>{entry.level.toUpperCase()}</Badge>
                    <Badge variant="neutral">{entry.category}</Badge>
                    <div className="text-xs text-[rgb(var(--muted))]">{formatLogTime(entry.ts)}</div>
                    {entry.request_id ? <Badge variant="neutral">req:{entry.request_id}</Badge> : null}
                    {entry.error_code ? <Badge variant="danger">code:{entry.error_code}</Badge> : null}
                  </div>
                  <div className="text-sm">{entry.message}</div>
                  {entry.meta ? (
                    <pre className="text-xs overflow-auto rounded-lg border border-[rgb(var(--border))] bg-[rgb(var(--card))] p-2">
                      {JSON.stringify(entry.meta, null, 2)}
                    </pre>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

function normalizeLogEntry(entry) {
  if (!entry || typeof entry !== 'object') return null
  const message = String(entry.message || '').trim()
  if (!message) return null
  const level = normalizeLevel(entry.level)
  const normalized = {
    ts: normalizeTimestamp(entry.ts),
    level,
    category: String(entry.category || 'runtime').trim() || 'runtime',
    message,
  }
  const requestId = String(entry.request_id || '').trim()
  if (requestId) normalized.request_id = requestId
  const errorCode = String(entry.error_code || '').trim()
  if (errorCode) normalized.error_code = errorCode
  if (entry.meta && typeof entry.meta === 'object') normalized.meta = entry.meta
  return normalized
}

function normalizeLevel(level) {
  const normalized = String(level || '').trim().toLowerCase()
  if (normalized === 'warning') return 'warn'
  if (LEVELS.includes(normalized)) return normalized
  return 'info'
}

function normalizeTimestamp(value) {
  const parsed = Number(value)
  if (Number.isFinite(parsed) && parsed > 0) return parsed
  return Date.now() / 1000
}

function formatLogTime(ts) {
  try {
    const date = new Date(Number(ts) * 1000)
    return `${date.toLocaleDateString()} ${date.toLocaleTimeString()}`
  } catch {
    return '-'
  }
}
