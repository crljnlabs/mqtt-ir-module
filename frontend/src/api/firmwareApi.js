import { requestJson } from './httpClient.js'

export function getFirmwareCatalog(agentType = 'esp32') {
  return requestJson(`/firmware?agent_type=${encodeURIComponent(agentType)}`)
}
