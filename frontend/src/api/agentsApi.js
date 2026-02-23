import {requestJson} from './httpClient.js'

export function listAgents() {
  return requestJson('/agents')
}

export function getAgent(agentId) {
  return requestJson(`/agents/${agentId}`)
}

export function getAgentDebug(agentId) {
  return requestJson(`/agents/${encodeURIComponent(agentId)}/debug`)
}

export function setAgentDebug(agentId, debug) {
  return requestJson(`/agents/${encodeURIComponent(agentId)}/debug`, {
    method: 'PUT',
    body: { debug: Boolean(debug) },
  })
}

export function getAgentLogs(agentId, limit = 100) {
  return requestJson(`/agents/${encodeURIComponent(agentId)}/logs?limit=${encodeURIComponent(String(limit))}`)
}

export function updateAgent(agentId, payload) {
  return requestJson(`/agents/${agentId}`, {
    method: 'PUT',
    body: payload,
  })
}

export function deleteAgent(agentId) {
  return requestJson(`/agents/${agentId}`, {
    method: 'DELETE',
  })
}

export function getAgentRuntimeConfig(agentId) {
  return requestJson(`/agents/${encodeURIComponent(agentId)}/runtime-config`)
}

export function updateAgentRuntimeConfig(agentId, payload) {
  return requestJson(`/agents/${encodeURIComponent(agentId)}/runtime-config`, {
    method: 'PUT',
    body: payload,
  })
}

export function rebootAgent(agentId) {
  return requestJson(`/agents/${encodeURIComponent(agentId)}/reboot`, {
    method: 'POST',
  })
}

export function otaUpdateAgent(agentId, payload) {
  return requestJson(`/agents/${encodeURIComponent(agentId)}/ota`, {
    method: 'POST',
    body: payload,
  })
}
