import { requestJson } from './httpClient.js'

/**
 * @param {{
 *   level?: string,
 *   source_type?: string,
 *   source_id?: string,
 *   category?: string,
 *   from_ts?: number,
 *   to_ts?: number,
 *   limit?: number,
 * }} params
 */
export function getLogs(params = {}) {
  const query = new URLSearchParams()
  if (params.level) query.set('level', params.level)
  if (params.source_type) query.set('source_type', params.source_type)
  if (params.source_id) query.set('source_id', params.source_id)
  if (params.category) query.set('category', params.category)
  if (params.from_ts != null) query.set('from_ts', String(params.from_ts))
  if (params.to_ts != null) query.set('to_ts', String(params.to_ts))
  if (params.limit != null) query.set('limit', String(params.limit))
  const qs = query.toString()
  return requestJson(`/logs${qs ? `?${qs}` : ''}`)
}

/**
 * @param {{
 *   level?: string,
 *   source_type?: string,
 *   source_id?: string,
 *   category?: string,
 *   from_ts?: number,
 *   to_ts?: number,
 * }} params
 */
export function clearLogs(params = {}) {
  const query = new URLSearchParams()
  if (params.level) query.set('level', params.level)
  if (params.source_type) query.set('source_type', params.source_type)
  if (params.source_id) query.set('source_id', params.source_id)
  if (params.category) query.set('category', params.category)
  if (params.from_ts != null) query.set('from_ts', String(params.from_ts))
  if (params.to_ts != null) query.set('to_ts', String(params.to_ts))
  const qs = query.toString()
  return requestJson(`/logs${qs ? `?${qs}` : ''}`, { method: 'DELETE' })
}
