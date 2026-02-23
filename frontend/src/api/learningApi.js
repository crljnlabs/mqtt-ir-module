import {requestJson} from './httpClient.js'

export function startLearning({remoteId, extend}) {
  return requestJson(
      '/learn/start',
      {method: 'POST', body: {remote_id: remoteId, extend: Boolean(extend)}})
}

export function stopLearning() {
  return requestJson('/learn/stop', {method: 'POST'})
}

export function getLearningSessionStatus() {
  return requestJson('/learn/status')
}

export function capturePress(
    {remoteId, takes, timeoutMs, overwrite, buttonName}) {
  return requestJson('/learn/capture', {
    method: 'POST',
    body: {
      remote_id: remoteId,
      mode: 'press',
      takes,
      timeout_ms: timeoutMs,
      overwrite: Boolean(overwrite),
      button_name: buttonName ?? null,
    },
  })
}

export function captureHold({remoteId, timeoutMs, overwrite, buttonName}) {
  return requestJson('/learn/capture', {
    method: 'POST',
    body: {
      remote_id: remoteId,
      mode: 'hold',
      takes: 1,
      timeout_ms: timeoutMs,
      overwrite: Boolean(overwrite),
      button_name: buttonName ?? null,
    },
  })
}
