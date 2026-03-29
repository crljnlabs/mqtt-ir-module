import { requestJson } from './httpClient.js'

export function getElectronicsStatus() {
  return requestJson('/status/electronics')
}

export function getLearningStatus() {
  return requestJson('/status/learning')
}

export function getMqttStatus() {
  return requestJson('/status/mqtt')
}

export function retryMqttConnection() {
  return requestJson('/mqtt/retry', { method: 'POST' })
}
