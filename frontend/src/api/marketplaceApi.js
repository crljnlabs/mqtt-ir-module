import { requestJson } from './httpClient.js'

export function listMarketplace({ q, category, brand, source } = {}) {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (category) params.set('category', category)
  if (brand) params.set('brand', brand)
  if (source) params.set('source', source)
  const qs = params.toString()
  return requestJson(`/marketplace/index${qs ? `?${qs}` : ''}`)
}

export function getMarketplaceCategories() {
  return requestJson('/marketplace/categories')
}

export function getMarketplaceBrands(category) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : ''
  return requestJson(`/marketplace/brands${qs}`)
}

export function getMarketplaceCount() {
  return requestJson('/marketplace/count')
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
