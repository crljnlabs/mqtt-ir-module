import { getAppConfig } from '../utils/appConfig.js'

function buildWebSocketUrl(path) {
  const { apiBaseUrl } = getAppConfig()
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  const base = apiBaseUrl.replace(/\/$/, '')

  if (base.startsWith('http://') || base.startsWith('https://')) {
    const url = new URL(`${base}${cleanPath}`)
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
    return url.toString()
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}${base}${cleanPath}`
}

export function createAgentLogsSocket(
  agentId,
  {
    onOpen,
    onClose,
    onError,
    onMessage,
  } = {},
) {
  const safeAgentId = encodeURIComponent(String(agentId || '').trim())
  const socket = new WebSocket(buildWebSocketUrl(`/agents/${safeAgentId}/logs/ws`))

  socket.onopen = () => onOpen?.()
  socket.onclose = () => onClose?.()
  socket.onerror = (event) => onError?.(event)
  socket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data)
      if (payload && typeof payload === 'object') onMessage?.(payload)
    } catch {
      // Ignore malformed payloads to keep the socket alive.
    }
  }

  return socket
}
