import { requestJson } from './httpClient.js'

export function listMarketplace({ q, category, source } = {}) {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (category) params.set('category', category)
  if (source) params.set('source', source)
  const qs = params.toString()
  return requestJson(`/marketplace/index${qs ? `?${qs}` : ''}`)
}

export function getMarketplaceCategories() {
  return requestJson('/marketplace/categories')
}

export function getMarketplaceSyncStatus() {
  return requestJson('/marketplace/sync/status')
}

export function triggerMarketplaceSync() {
  return requestJson('/marketplace/sync', { method: 'POST' })
}

export function getInstalledMarketplacePaths() {
  return requestJson('/marketplace/installed-paths')
}

export function installMarketplaceRemote({ path, remote_name }) {
  return requestJson('/marketplace/install', {
    method: 'POST',
    body: { path, remote_name },
  })
}
