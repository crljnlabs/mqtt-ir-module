import {requestJson} from './httpClient.js'

export function getVersion() {
  return requestJson('/version')
}
