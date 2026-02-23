import { requestJson } from './httpClient.js'

export function getPairingStatus() {
  return requestJson('/status/pairing')
}

export function openPairing() {
  return requestJson('/pairing/open', {
    method: 'POST',
    body: {},
  })
}

export function closePairing() {
  return requestJson('/pairing/close', {
    method: 'POST',
    body: {},
  })
}

export function acceptPairing(agentId) {
  return requestJson(`/pairing/accept/${encodeURIComponent(agentId)}`, {
    method: 'POST',
    body: {},
  })
}
