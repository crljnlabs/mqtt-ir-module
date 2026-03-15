import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiChevronLeft, mdiDownload, mdiRefresh, mdiTrashCan } from '@mdi/js'

import { getLogs, clearLogs } from '../api/logsApi.js'
import { listAgents, getAgentDebug, setAgentDebug } from '../api/agentsApi.js'
import { createLogsSocket } from '../api/logsSocket.js'
import { Button } from '../components/ui/Button.jsx'
import { Card, CardBody, CardHeader, CardTitle } from '../components/ui/Card.jsx'
import { Badge } from '../components/ui/Badge.jsx'
import { TextField } from '../components/ui/TextField.jsx'
import { ConfirmDialog } from '../components/ui/ConfirmDialog.jsx'

const MAX_LIVE_LOGS = 500
const LEVELS = ['debug', 'info', 'warn', 'error']
const LEVEL_BADGE_VARIANT = {
  debug: 'neutral',
  info: 'success',
  warn: 'warning',
  error: 'danger',
}
const DEFAULT_CATEGORIES = ['send', 'learn', 'pairing', 'runtime', 'transport', 'system']

export function LogsPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()

  // Pre-filter from URL param ?source_id=xxx (used when navigating from AgentPage)
  const preSourceId = searchParams.get('source_id') || null

  // ── Live log state ──────────────────────────────────────────────────────────
  const [liveLogs, setLiveLogs] = useState([])
  const [socketConnected, setSocketConnected] = useState(false)
  const reconnectTimerRef = useRef(null)
  const socketRef = useRef(null)

  // ── Filter state ────────────────────────────────────────────────────────────
  const [search, setSearch] = useState('')
  // Multi-select: null means "all selected" (no filter)
  const [selectedLevels, setSelectedLevels] = useState([])       // [] = all
  const [selectedSources, setSelectedSources] = useState(        // [] = all
    preSourceId ? [preSourceId] : []
  )
  const [selectedCategories, setSelectedCategories] = useState([]) // [] = all
  const [fromTs, setFromTs] = useState(() => {
    const d = new Date()
    d.setHours(d.getHours() - 1)
    return toDatetimeLocalValue(d)
  })
  const [toTs, setToTs] = useState('')  // empty = live mode

  // ── UI state ────────────────────────────────────────────────────────────────
  const [autoScroll, setAutoScroll] = useState(true)
  const [confirmClearOpen, setConfirmClearOpen] = useState(false)
  const [openDropdown, setOpenDropdown] = useState(null)  // 'level' | 'source' | 'category' | null
  const [toTsEditing, setToTsEditing] = useState(false)
  const toTsInputRef = useRef(null)
  const logContainerRef = useRef(null)
  const dropdownRef = useRef(null)

  const isLiveMode = !toTs

  // ── Agents list (for source filter labels) ──────────────────────────────────
  const agentsQuery = useQuery({
    queryKey: ['agents'],
    queryFn: listAgents,
    staleTime: 30_000,
  })
  const agents = useMemo(() => {
    const list = Array.isArray(agentsQuery.data) ? agentsQuery.data : []
    return list.filter((a) => !a.pending)
  }, [agentsQuery.data])

  const sourceOptions = useMemo(() => {
    const opts = [{ value: 'hub', label: 'Hub' }]
    for (const agent of agents) {
      const id = String(agent.agent_id || '')
      const label = String(agent.name || agent.agent_id || id)
      opts.push({ value: id, label })
    }
    return opts
  }, [agents])

  // Debug toggle — visible only when exactly one MQTT agent is selected
  const singleSelectedAgent = selectedSources.length === 1
    ? agents.find((a) => a.agent_id === selectedSources[0])
    : null
  const isSingleMqttAgent = singleSelectedAgent?.transport === 'mqtt'

  const debugQuery = useQuery({
    queryKey: ['agent-debug', singleSelectedAgent?.agent_id],
    queryFn: () => getAgentDebug(singleSelectedAgent.agent_id),
    enabled: Boolean(isSingleMqttAgent),
  })
  const debugMutation = useMutation({
    mutationFn: (enabled) => setAgentDebug(singleSelectedAgent.agent_id, enabled),
    onSuccess: (payload) => {
      queryClient.setQueryData(['agent-debug', singleSelectedAgent.agent_id], payload)
    },
  })

  // ── Build query params from filter state ────────────────────────────────────
  const queryParams = useMemo(() => {
    const params = {}
    if (selectedLevels.length > 0) params.level = selectedLevels.join(',')
    if (selectedSources.length > 0) {
      const sourceTypes = []
      const sourceIds = []
      for (const s of selectedSources) {
        if (s === 'hub') {
          sourceTypes.push('hub')
        } else {
          sourceTypes.push('agent')
          sourceIds.push(s)
        }
      }
      // Deduplicate
      if (sourceTypes.length > 0) params.source_type = [...new Set(sourceTypes)].join(',')
      if (sourceIds.length > 0) params.source_id = sourceIds.join(',')
    }
    if (selectedCategories.length > 0) params.category = selectedCategories.join(',')
    if (fromTs) params.from_ts = toUnixTs(fromTs)
    if (!isLiveMode && toTs) params.to_ts = toUnixTs(toTs)
    params.limit = 500
    return params
  }, [selectedLevels, selectedSources, selectedCategories, fromTs, toTs, isLiveMode])

  // ── Snapshot fetch (initial load + refresh) ─────────────────────────────────
  const snapshotQuery = useQuery({
    queryKey: ['logs', queryParams],
    queryFn: () => getLogs(queryParams),
    staleTime: 0,
  })
  const snapshotLogs = useMemo(() => {
    const items = Array.isArray(snapshotQuery.data?.items) ? snapshotQuery.data.items : []
    return items.map(normalizeLogEntry).filter(Boolean)
  }, [snapshotQuery.data])

  // ── WebSocket (live mode only) ───────────────────────────────────────────────
  useEffect(() => {
    if (!isLiveMode) {
      // Disconnect if switching out of live mode
      if (socketRef.current) {
        socketRef.current.close()
        socketRef.current = null
      }
      setSocketConnected(false)
      setLiveLogs([])
      return undefined
    }

    let cancelled = false

    const connect = () => {
      if (cancelled) return
      const socket = createLogsSocket({
        onOpen: () => setSocketConnected(true),
        onClose: () => {
          setSocketConnected(false)
          if (cancelled) return
          reconnectTimerRef.current = window.setTimeout(connect, 1500)
        },
        onError: () => setSocketConnected(false),
        onMessage: (payload) => {
          const normalized = normalizeLogEntry(payload)
          if (!normalized) return
          setLiveLogs((prev) => {
            const next = [...prev, normalized]
            return next.length > MAX_LIVE_LOGS ? next.slice(next.length - MAX_LIVE_LOGS) : next
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
  }, [isLiveMode])

  // ── Merge snapshot + live, then apply client-side filters ───────────────────
  const allLogs = useMemo(() => {
    const merged = [...snapshotLogs, ...liveLogs]
    const deduped = []
    const seen = new Set()
    for (const entry of merged) {
      const key = `${entry.ts}|${entry.level}|${entry.source_type}|${entry.source_id}|${entry.category}|${entry.message}|${entry.request_id || ''}|${entry.error_code || ''}`
      if (seen.has(key)) continue
      seen.add(key)
      deduped.push(entry)
    }
    return deduped
  }, [snapshotLogs, liveLogs])

  const filteredLogs = useMemo(() => {
    const query = search.trim().toLowerCase()
    return allLogs.filter((entry) => {
      // Apply level/source/category client-side — needed for live WS logs which arrive unfiltered
      if (selectedLevels.length > 0 && !selectedLevels.includes(entry.level)) return false
      if (selectedSources.length > 0) {
        const matchesHub = entry.source_type === 'hub' && selectedSources.includes('hub')
        const matchesAgent = entry.source_type === 'agent' && selectedSources.includes(String(entry.source_id || ''))
        if (!matchesHub && !matchesAgent) return false
      }
      if (selectedCategories.length > 0 && !selectedCategories.includes(entry.category)) return false
      if (!query) return true
      const haystack = [
        entry.message,
        entry.category,
        entry.source_id || '',
        entry.source_type || '',
        entry.error_code || '',
        entry.request_id || '',
        JSON.stringify(entry.meta || {}),
      ].join(' ').toLowerCase()
      return haystack.includes(query)
    })
  }, [allLogs, search, selectedLevels, selectedSources, selectedCategories])

  // ── Auto-scroll ──────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!autoScroll) return
    const container = logContainerRef.current
    if (!container) return
    container.scrollTop = container.scrollHeight
  }, [autoScroll, filteredLogs.length])

  // ── Close dropdown on outside click ─────────────────────────────────────────
  useEffect(() => {
    if (!openDropdown) return
    const handler = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setOpenDropdown(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [openDropdown])

  // ── Known categories (from logs + defaults) ──────────────────────────────────
  const knownCategories = useMemo(() => {
    const values = new Set(DEFAULT_CATEGORIES)
    for (const entry of allLogs) {
      const c = String(entry.category || '').trim()
      if (c) values.add(c)
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b))
  }, [allLogs])

  // ── Back navigation ──────────────────────────────────────────────────────────
  const backTarget = useMemo(() => {
    const fromState = location.state?.from
    if (typeof fromState === 'string' && fromState.trim()) return fromState
    return null
  }, [location.state])

  // ── Clear logs ───────────────────────────────────────────────────────────────
  const clearMutation = useMutation({
    mutationFn: () => clearLogs(buildClearParams(queryParams)),
    onSuccess: () => {
      setLiveLogs([])
      queryClient.invalidateQueries({ queryKey: ['logs'] })
      setConfirmClearOpen(false)
    },
  })

  // ── Export ───────────────────────────────────────────────────────────────────
  const exportLogs = () => {
    const blob = new Blob([JSON.stringify(filteredLogs, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const confirmClearDescription = buildClearDescription(queryParams, sourceOptions)

  return (
    <div className="space-y-4">
      {/* ── Header ── */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          {backTarget ? (
            <Button variant="ghost" size="sm" onClick={() => navigate(backTarget)}>
              <Icon path={mdiChevronLeft} size={0.9} />
              Back
            </Button>
          ) : null}
          <div className="truncate font-semibold">Logs</div>
        </div>
        <div className="flex items-center gap-2">
          {isSingleMqttAgent ? (
            <Button
              size="sm"
              variant={debugQuery.data?.debug ? 'primary' : 'secondary'}
              disabled={debugQuery.isLoading || debugMutation.isPending}
              onClick={() => debugMutation.mutate(!(debugQuery.data?.debug ?? false))}
            >
              Agent Debug: {debugQuery.data?.debug ? 'ON' : 'OFF'}
            </Button>
          ) : null}
          {isLiveMode ? (
            <Badge variant={socketConnected ? 'success' : 'warning'}>
              {socketConnected ? 'Live' : 'Reconnecting'}
            </Badge>
          ) : null}
        </div>
      </div>

      {/* ── Filters card ── */}
      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: ['logs'] })
              }}
              disabled={snapshotQuery.isFetching}
            >
              <Icon path={mdiRefresh} size={0.8} />
              Refresh
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={exportLogs}
              disabled={filteredLogs.length === 0}
            >
              <Icon path={mdiDownload} size={0.8} />
              Export
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setConfirmClearOpen(true)}
            >
              <Icon path={mdiTrashCan} size={0.8} />
              Clear
            </Button>
          </div>
        </CardHeader>
        <CardBody className="space-y-3">
          {/* Search */}
          <TextField
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
            clearLabel={t('common.clear')}
            placeholder="Search message, category, source, request id..."
          />

          {/* Multi-select dropdowns row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3" ref={dropdownRef}>
            <MultiSelectDropdown
              label="Source"
              options={sourceOptions}
              selected={selectedSources}
              onChange={setSelectedSources}
              open={openDropdown === 'source'}
              onToggle={() => setOpenDropdown((prev) => prev === 'source' ? null : 'source')}
            />
            <MultiSelectDropdown
              label="Level"
              options={LEVELS.map((l) => ({ value: l, label: l.toUpperCase() }))}
              selected={selectedLevels}
              onChange={setSelectedLevels}
              open={openDropdown === 'level'}
              onToggle={() => setOpenDropdown((prev) => prev === 'level' ? null : 'level')}
            />
            <MultiSelectDropdown
              label="Category"
              options={knownCategories.map((c) => ({ value: c, label: c }))}
              selected={selectedCategories}
              onChange={setSelectedCategories}
              open={openDropdown === 'category'}
              onToggle={() => setOpenDropdown((prev) => prev === 'category' ? null : 'category')}
            />
          </div>

          {/* Time range row */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end">
            <div>
              <label className="block text-xs text-[rgb(var(--muted))] mb-1">From</label>
              <input
                type="datetime-local"
                value={fromTs}
                onChange={(e) => setFromTs(e.target.value)}
                className="w-full rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] px-3 py-2 text-sm text-[rgb(var(--fg))] focus:outline-none focus:ring-2 focus:ring-[rgb(var(--primary))]"
              />
            </div>
            <div>
              <label className="block text-xs text-[rgb(var(--muted))] mb-1">To</label>
              {toTs || toTsEditing ? (
                <input
                  ref={toTsInputRef}
                  type="datetime-local"
                  value={toTs}
                  onChange={(e) => setToTs(e.target.value)}
                  onBlur={() => { if (!toTs) setToTsEditing(false) }}
                  className="w-full rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] px-3 py-2 text-sm text-[rgb(var(--fg))] focus:outline-none focus:ring-2 focus:ring-[rgb(var(--primary))]"
                />
              ) : (
                <div
                  onClick={() => {
                    setToTsEditing(true)
                    requestAnimationFrame(() => {
                      toTsInputRef.current?.focus()
                      toTsInputRef.current?.showPicker?.()
                    })
                  }}
                  className="w-full rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] px-3 py-2 text-sm text-[rgb(var(--muted))] cursor-pointer select-none"
                >
                  Live
                </div>
              )}
            </div>
            <div className="flex items-end">
              <Button
                variant={autoScroll ? 'primary' : 'secondary'}
                size="sm"
                className="h-[2.625rem]"
                onClick={() => setAutoScroll((prev) => !prev)}
              >
                Auto-scroll
              </Button>
              {toTs ? (
                <Button
                  variant="secondary"
                  size="sm"
                  className="ml-2 h-[2.625rem]"
                  onClick={() => { setToTs(''); setToTsEditing(false) }}
                >
                  Back to live
                </Button>
              ) : null}
            </div>
          </div>
        </CardBody>
      </Card>

      {/* ── Events card ── */}
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
                <LogEntry key={`${entry.ts}-${entry.source_type}-${entry.source_id}-${entry.level}-${entry.message}-${index}`} entry={entry} sourceOptions={sourceOptions} />
              ))}
            </div>
          )}
        </CardBody>
      </Card>

      {/* ── Clear confirm dialog ── */}
      <ConfirmDialog
        open={confirmClearOpen}
        title="Clear logs"
        body={confirmClearDescription}
        confirmText="Delete"
        confirmVariant="danger"
        onConfirm={() => clearMutation.mutate()}
        onCancel={() => setConfirmClearOpen(false)}
      />
    </div>
  )
}

// ── LogEntry sub-component ──────────────────────────────────────────────────

function LogEntry({ entry, sourceOptions }) {
  const sourceLabel = getSourceLabel(entry.source_type, entry.source_id, sourceOptions)

  return (
    <div className="rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] p-3 space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={LEVEL_BADGE_VARIANT[entry.level] || 'neutral'}>{entry.level.toUpperCase()}</Badge>
        <Badge variant="neutral">{entry.category}</Badge>
        <Badge variant={entry.source_type === 'hub' ? 'warning' : 'neutral'}>{sourceLabel}</Badge>
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
  )
}

// ── MultiSelectDropdown sub-component ──────────────────────────────────────

function MultiSelectDropdown({ label, options, selected, onChange, open, onToggle }) {
  const allSelected = selected.length === 0

  const toggle = (value) => {
    if (selected.includes(value)) {
      const next = selected.filter((v) => v !== value)
      onChange(next)
    } else {
      onChange([...selected, value])
    }
  }

  const displayLabel = allSelected
    ? `${label}: All`
    : `${label}: ${selected.length} selected`

  return (
    <div className="relative">
      <button
        type="button"
        onClick={onToggle}
        className="w-full h-11 flex items-center justify-between rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--bg))] px-3 py-2 text-sm text-left text-[rgb(var(--fg))] focus:outline-none focus:ring-2 focus:ring-[rgb(var(--primary))]"
      >
        <span className="truncate">{displayLabel}</span>
        <span className="ml-2 text-[rgb(var(--muted))]">{open ? '▲' : '▼'}</span>
      </button>
      {open ? (
        <div className="absolute z-50 mt-1 w-full rounded-xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] shadow-lg">
          <button
            type="button"
            className="w-full px-3 py-2 text-sm text-left text-[rgb(var(--fg))] hover:bg-[rgb(var(--bg))] flex items-center gap-2"
            onClick={() => onChange([])}
          >
            <span className="w-4">{allSelected ? '✓' : ''}</span>
            All
          </button>
          {options.map((opt) => {
            const checked = selected.includes(opt.value)
            return (
              <button
                key={opt.value}
                type="button"
                className="w-full px-3 py-2 text-sm text-left text-[rgb(var(--fg))] hover:bg-[rgb(var(--bg))] flex items-center gap-2"
                onClick={() => toggle(opt.value)}
              >
                <span className="w-4">{checked ? '✓' : ''}</span>
                {opt.label}
              </button>
            )
          })}
        </div>
      ) : null}
    </div>
  )
}

// ── Helpers ─────────────────────────────────────────────────────────────────

function normalizeLogEntry(entry) {
  if (!entry || typeof entry !== 'object') return null
  const message = String(entry.message || '').trim()
  if (!message) return null
  const level = normalizeLevel(entry.level)
  const normalized = {
    ts: normalizeTimestamp(entry.ts),
    level,
    source_type: String(entry.source_type || 'agent').trim() || 'agent',
    source_id: String(entry.source_id || '').trim() || null,
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

function toDatetimeLocalValue(date) {
  // Format: YYYY-MM-DDTHH:mm (local time, no seconds)
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function toUnixTs(datetimeLocalValue) {
  if (!datetimeLocalValue) return null
  return new Date(datetimeLocalValue).getTime() / 1000
}

function getSourceLabel(sourceType, sourceId, sourceOptions) {
  if (sourceType === 'hub') return 'Hub'
  if (!sourceId) return 'Agent'
  const opt = sourceOptions.find((o) => o.value === sourceId)
  return opt ? opt.label : sourceId
}

/**
 * Build params for the DELETE /logs call — only pass filter params that
 * map directly to DB columns. The client-side `search` filter is not sent.
 */
function buildClearParams(queryParams) {
  const params = {}
  if (queryParams.level) params.level = queryParams.level
  if (queryParams.source_type) params.source_type = queryParams.source_type
  if (queryParams.source_id) params.source_id = queryParams.source_id
  if (queryParams.category) params.category = queryParams.category
  if (queryParams.from_ts != null) params.from_ts = queryParams.from_ts
  if (queryParams.to_ts != null) params.to_ts = queryParams.to_ts
  return params
}

function buildClearDescription(queryParams, sourceOptions) {
  const parts = []
  if (queryParams.source_type || queryParams.source_id) {
    const ids = queryParams.source_id ? queryParams.source_id.split(',') : []
    const types = queryParams.source_type ? queryParams.source_type.split(',') : []
    const labels = []
    if (types.includes('hub')) labels.push('Hub')
    for (const id of ids) {
      const opt = sourceOptions.find((o) => o.value === id)
      labels.push(opt ? opt.label : id)
    }
    if (labels.length > 0) parts.push(`Source: ${labels.join(', ')}`)
  }
  if (queryParams.level) parts.push(`Level: ${queryParams.level}`)
  if (queryParams.category) parts.push(`Category: ${queryParams.category}`)
  if (queryParams.from_ts != null) parts.push(`From: ${new Date(queryParams.from_ts * 1000).toLocaleString()}`)
  if (queryParams.to_ts != null) parts.push(`To: ${new Date(queryParams.to_ts * 1000).toLocaleString()}`)

  if (parts.length === 0) return 'This will permanently delete all log entries.'
  return `This will permanently delete log entries matching: ${parts.join(' · ')}`
}
