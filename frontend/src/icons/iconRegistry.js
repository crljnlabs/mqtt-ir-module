import * as MdiIcons from '@mdi/js'

const MDI_PREFIX = 'mdi:'
let mdiIconEntriesCache = null
let mdiIconMapCache = null

export function normalizeMdiId(value) {
  if (!value || typeof value !== 'string') return null
  const normalized = value.trim().toLowerCase()
  if (!normalized) return null
  return normalized.startsWith(MDI_PREFIX) ? normalized : `${MDI_PREFIX}${normalized}`
}

function toMdiId(exportKey) {
  if (!exportKey || !exportKey.startsWith('mdi')) return null
  const raw = exportKey.slice(3)
  if (!raw) return null
  // Convert MDI export keys (mdiRemoteTv) into ids (mdi:remote-tv).
  const kebab = raw
    .replace(/([a-z0-9])([A-Z])/g, '$1-$2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1-$2')
    .replace(/([a-zA-Z])([0-9])/g, '$1-$2')
    .replace(/([0-9])([a-zA-Z])/g, '$1-$2')
    .replace(/-+/g, '-')
    .toLowerCase()
  return `${MDI_PREFIX}${kebab}`
}

function buildMdiIconEntries() {
  const entries = Object.entries(MdiIcons)
    .filter(([key, value]) => key.startsWith('mdi') && typeof value === 'string')
    .map(([key, path]) => {
      const id = toMdiId(key)
      if (!id) return null
      return { id, name: id.slice(MDI_PREFIX.length), path }
    })
    .filter(Boolean)

  entries.sort((a, b) => a.name.localeCompare(b.name))
  return entries
}

function getMdiIconEntriesInternal() {
  if (!mdiIconEntriesCache) {
    // Cache the full MDI registry so it is built once per session.
    mdiIconEntriesCache = buildMdiIconEntries()
  }
  return mdiIconEntriesCache
}

export function getMdiIconEntries() {
  return getMdiIconEntriesInternal()
}

function getMdiIconMap() {
  if (!mdiIconMapCache) {
    const map = new Map()
    getMdiIconEntriesInternal().forEach((entry) => {
      if (!map.has(entry.id)) map.set(entry.id, entry.path)
    })
    mdiIconMapCache = map
  }
  return mdiIconMapCache
}

export function getMdiIconPath(value) {
  const normalized = normalizeMdiId(value)
  if (!normalized) return null
  return getMdiIconMap().get(normalized) ?? null
}

export const DEFAULT_REMOTE_ICON = 'remoteTv'
export const DEFAULT_BUTTON_ICON = 'tapButton'
export const DEFAULT_AGENT_ICON = 'mdi:robot-outline'

export const ICONS = [
  // Remote
  { key: 'remoteTv', category: 'remote', path: MdiIcons.mdiRemoteTv },
  { key: 'remote', category: 'remote', path: MdiIcons.mdiRemote },
  { key: 'tv', category: 'remote', path: MdiIcons.mdiTelevision },

  // Power / volume
  { key: 'power', category: 'power', path: MdiIcons.mdiPower },
  { key: 'standby', category: 'power', path: MdiIcons.mdiPowerStandby },
  { key: 'volumeUp', category: 'volume', path: MdiIcons.mdiVolumePlus },
  { key: 'volumeDown', category: 'volume', path: MdiIcons.mdiVolumeMinus },
  { key: 'mute', category: 'volume', path: MdiIcons.mdiVolumeMute },

  // Navigation
  { key: 'up', category: 'navigation', path: MdiIcons.mdiChevronUp },
  { key: 'down', category: 'navigation', path: MdiIcons.mdiChevronDown },
  { key: 'left', category: 'navigation', path: MdiIcons.mdiChevronLeft },
  { key: 'right', category: 'navigation', path: MdiIcons.mdiChevronRight },
  { key: 'ok', category: 'navigation', path: MdiIcons.mdiCheckCircleOutline },
  { key: 'home', category: 'navigation', path: MdiIcons.mdiHomeOutline },
  { key: 'back', category: 'navigation', path: MdiIcons.mdiArrowLeft },
  { key: 'menu', category: 'navigation', path: MdiIcons.mdiMenu },

  // Media
  { key: 'play', category: 'media', path: MdiIcons.mdiPlay },
  { key: 'pause', category: 'media', path: MdiIcons.mdiPause },
  { key: 'stop', category: 'media', path: MdiIcons.mdiStop },
  { key: 'rewind', category: 'media', path: MdiIcons.mdiRewind },
  { key: 'fastForward', category: 'media', path: MdiIcons.mdiFastForward },
  { key: 'next', category: 'media', path: MdiIcons.mdiSkipNext },
  { key: 'previous', category: 'media', path: MdiIcons.mdiSkipPrevious },

  // Input / misc
  { key: 'inputHdmi', category: 'input', path: MdiIcons.mdiVideoInputHdmi },
  { key: 'info', category: 'input', path: MdiIcons.mdiInformationOutline },
  { key: 'settings', category: 'input', path: MdiIcons.mdiCogOutline },
  { key: 'channel', category: 'input', path: MdiIcons.mdiNumeric },

  // Default button icon
  { key: 'tapButton', category: 'default', path: MdiIcons.mdiGestureTapButton },
]

export const ICON_CATEGORIES = Array.from(new Set(ICONS.map((i) => i.category)))

export function findIconPath(iconKey) {
  const found = ICONS.find((i) => i.key === iconKey)
  if (found) return found.path
  const mdiPath = getMdiIconPath(iconKey)
  if (mdiPath) return mdiPath
  const fallback = ICONS.find((i) => i.key === DEFAULT_BUTTON_ICON)
  return fallback ? fallback.path : MdiIcons.mdiGestureTapButton
}
