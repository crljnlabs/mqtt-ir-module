export function normalizeInstallationStatus(installation) {
  const status = String(installation?.status || '').trim().toLowerCase()
  return status || 'idle'
}

export function isInstallationInProgress(installation) {
  if (typeof installation?.in_progress === 'boolean') {
    return installation.in_progress
  }
  const status = normalizeInstallationStatus(installation)
  return status === 'started' || status === 'downloading' || status === 'installing'
}

export function installationBadgeVariant(installation) {
  const status = normalizeInstallationStatus(installation)
  if (status === 'failure') return 'danger'
  if (status === 'finished') return 'success'
  if (status === 'cancelled') return 'neutral'
  if (status === 'idle') return 'neutral'
  return 'warning'
}

export function installationBadgeLabel(installation) {
  const status = normalizeInstallationStatus(installation)
  if (status === 'idle') return ''
  const progress = Number.isFinite(Number(installation?.progress_pct)) ? Math.max(0, Math.min(100, Number(installation.progress_pct))) : null
  const base = status.toUpperCase()
  if (progress == null || status === 'failure' || status === 'finished' || status === 'cancelled') {
    return base
  }
  return `${base} ${Math.round(progress)}%`
}
