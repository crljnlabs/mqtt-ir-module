import React, { useEffect, useMemo, useState } from 'react'
import Icon from '@mdi/react'
import { useTranslation } from 'react-i18next'
import { Drawer } from '../ui/Drawer.jsx'
import { TextField } from '../ui/TextField.jsx'
import { Button } from '../ui/Button.jsx'
import { ICONS, ICON_CATEGORIES, getMdiIconEntries, normalizeMdiId } from '../../icons/iconRegistry.js'

const DEFAULT_CATEGORY = 'all'
const MAX_VISIBLE_ITEMS = 100
// Slightly larger previews help thin MDI glyphs remain legible.
const ICON_PREVIEW_SIZE = 1.3
const CURATED_PATHS = new Set(ICONS.map((icon) => icon.path))

const normalizeCuratedQuery = (value) => value.trim().toLowerCase()
const normalizeMdiQuery = (value) =>
  value
    .trim()
    .toLowerCase()
    .replace(/[_\s]+/g, '-')
    .replace(/-+/g, '-')
const stripMdiPrefix = (value) => (value.startsWith('mdi:') ? value.slice(4) : value)

export function IconPicker({ open, title, initialIconKey, onClose, onSelect, onBack }) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState(DEFAULT_CATEGORY)
  const [page, setPage] = useState(1)

  useEffect(() => {
    if (!open) {
      // Reset picker state when the drawer closes.
      setQuery('')
      setCategory(DEFAULT_CATEGORY)
      setPage(1)
    }
  }, [open])

  useEffect(() => {
    // Reset paging whenever the filters change.
    setPage(1)
  }, [query, category])

  const curatedQuery = useMemo(() => normalizeCuratedQuery(query), [query])
  const mdiQuery = useMemo(() => normalizeMdiQuery(query), [query])

  const mdiIcons = useMemo(() => (open ? getMdiIconEntries() : []), [open])
  const mdiIdByPath = useMemo(() => {
    const map = new Map()
    mdiIcons.forEach((icon) => {
      if (!map.has(icon.path)) map.set(icon.path, icon.id)
    })
    return map
  }, [mdiIcons])

  const filteredPinned = useMemo(() => {
    const q = curatedQuery
    const qMdi = mdiQuery
    const qMdiName = stripMdiPrefix(mdiQuery)
    const hasQuery = q.length > 0
    const matches = ICONS.filter((icon) => {
      const matchesCategory = category === DEFAULT_CATEGORY ? true : icon.category === category
      if (!hasQuery) return matchesCategory
      const label = t(`icons.labels.${icon.key}`).toLowerCase()
      const labelMdi = normalizeMdiQuery(label)
      const key = icon.key.toLowerCase()
      const mdiId = mdiIdByPath.get(icon.path) || ''
      const mdiName = stripMdiPrefix(mdiId)
      const matchesLabel = label.includes(q) || labelMdi.includes(qMdiName)
      const matchesKey = key.includes(q)
      const matchesMdi = mdiId.includes(qMdi) || mdiName.includes(qMdiName)
      return matchesCategory && (matchesLabel || matchesKey || matchesMdi)
    })

    if (!hasQuery) return matches

    const rankMatch = (icon) => {
      const label = t(`icons.labels.${icon.key}`).toLowerCase()
      const labelMdi = normalizeMdiQuery(label)
      const key = icon.key.toLowerCase()
      const mdiId = mdiIdByPath.get(icon.path) || ''
      const mdiName = stripMdiPrefix(mdiId)
      if (label === q || labelMdi === qMdiName || key === q || mdiId === qMdi || mdiName === qMdiName) return 0
      if (label.startsWith(q) || labelMdi.startsWith(qMdiName) || key.startsWith(q) || mdiId.startsWith(qMdi) || mdiName.startsWith(qMdiName)) return 1
      return 2
    }

    return matches.sort((a, b) => {
      const rank = rankMatch(a) - rankMatch(b)
      if (rank !== 0) return rank
      const labelA = t(`icons.labels.${a.key}`).toLowerCase()
      const labelB = t(`icons.labels.${b.key}`).toLowerCase()
      return labelA.localeCompare(labelB)
    })
  }, [curatedQuery, mdiQuery, category, t, mdiIdByPath])

  const filteredMdi = useMemo(() => {
    if (!mdiIcons.length) return []
    const qRaw = mdiQuery
    const qName = stripMdiPrefix(qRaw)
    const matches = mdiIcons.filter((icon) => {
      if (CURATED_PATHS.has(icon.path)) return false
      if (!qRaw) return true
      return icon.id.includes(qRaw) || icon.name.includes(qName)
    })
    if (!qRaw) return matches

    const exactId = qName ? `mdi:${qName}` : qRaw
    // Prefer exact matches first, then prefix matches, then the rest.
    const rankMatch = (icon) => {
      if (icon.id === exactId || icon.name === qName) return 0
      if (icon.name.startsWith(qName) || icon.id.startsWith(exactId)) return 1
      return 2
    }

    return matches.sort((a, b) => {
      const rank = rankMatch(a) - rankMatch(b)
      if (rank !== 0) return rank
      return a.name.localeCompare(b.name)
    })
  }, [mdiIcons, mdiQuery])

  const categories = useMemo(() => [DEFAULT_CATEGORY, ...ICON_CATEGORIES], [])

  const selectedMdiId = useMemo(() => {
    if (typeof initialIconKey !== 'string') return null
    const trimmed = initialIconKey.trim().toLowerCase()
    if (!trimmed.startsWith('mdi:')) return null
    return normalizeMdiId(trimmed)
  }, [initialIconKey])

  // Keep total visible icons under the hard cap by reserving slots for curated icons.
  const maxMdiItems = Math.max(0, MAX_VISIBLE_ITEMS - filteredPinned.length)
  const pageCount = useMemo(() => {
    if (maxMdiItems === 0) return 1
    return Math.max(1, Math.ceil(filteredMdi.length / maxMdiItems))
  }, [filteredMdi.length, maxMdiItems])
  const currentPage = Math.min(page, pageCount)

  useEffect(() => {
    setPage((prev) => Math.min(prev, pageCount))
  }, [pageCount])

  const pageItems = useMemo(() => {
    if (maxMdiItems === 0) return []
    const start = (currentPage - 1) * maxMdiItems
    return filteredMdi.slice(start, start + maxMdiItems)
  }, [filteredMdi, currentPage, maxMdiItems])

  const canGoPrev = currentPage > 1
  const canGoNext = currentPage < pageCount

  return (
    <Drawer
      open={open}
      title={title}
      onClose={onClose}
      onBack={onBack}
      footer={
        <div className="flex justify-end">
          <Button variant="secondary" onClick={onClose}>
            {t('common.close')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <TextField
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onClear={() => setQuery('')}
          clearLabel={t('common.clear')}
          placeholder={t('icons.picker.searchPlaceholder')}
          aria-label={t('icons.picker.searchPlaceholder')}
        />

        <div className="flex gap-2 flex-wrap">
          {categories.map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => setCategory(c)}
              aria-pressed={c === category}
              className={[
                'px-3 py-2 rounded-full text-xs font-semibold border',
                c === category ? 'border-[rgb(var(--primary))] text-[rgb(var(--primary))]' : 'border-[rgb(var(--border))] text-[rgb(var(--muted))]',
              ].join(' ')}
            >
              {t(`icons.categories.${c}`)}
            </button>
          ))}
        </div>

        {filteredPinned.length > 0 ? (
          <div className="space-y-2">
            <div className="text-xs font-semibold text-[rgb(var(--muted))]">
              {t('icons.picker.featuredTitle')}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {filteredPinned.map((item) => (
                <button
                  key={item.key}
                  type="button"
                  aria-pressed={item.key === initialIconKey}
                  className={[
                    'rounded-2xl border p-3 text-center hover:opacity-95',
                    item.key === initialIconKey ? 'border-[rgb(var(--primary))]' : 'border-[rgb(var(--border))]',
                  ].join(' ')}
                  onClick={() => onSelect(item.key)}
                >
                  <div className="flex flex-col items-center gap-2">
                    <Icon path={item.path} size={ICON_PREVIEW_SIZE} />
                    <div className="text-xs font-semibold truncate w-full">{t(`icons.labels.${item.key}`)}</div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="text-xs font-semibold text-[rgb(var(--muted))]">
              {t('icons.picker.mdiTitle')}
            </div>
            <div className="text-[10px] text-[rgb(var(--muted))]">
              {t('icons.picker.resultCount', { count: pageItems.length, total: filteredMdi.length })}
            </div>
          </div>

          {filteredMdi.length === 0 ? (
            <div className="text-xs text-[rgb(var(--muted))]">{t('icons.picker.empty')}</div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {pageItems.map((icon) => (
                <button
                  key={icon.id}
                  type="button"
                  aria-pressed={selectedMdiId === icon.id}
                  className={[
                    'rounded-2xl border p-3 text-center hover:opacity-95',
                    selectedMdiId === icon.id ? 'border-[rgb(var(--primary))]' : 'border-[rgb(var(--border))]',
                  ].join(' ')}
                  onClick={() => onSelect(icon.id)}
                >
                  <div className="flex flex-col items-center gap-2">
                    <Icon path={icon.path} size={ICON_PREVIEW_SIZE} />
                    <div className="text-xs font-semibold truncate w-full">{icon.name}</div>
                  </div>
                </button>
              ))}
            </div>
          )}

          <div className="flex items-center justify-between">
            <div className="text-[10px] text-[rgb(var(--muted))]">
              {t('icons.picker.pageStatus', { current: currentPage, total: pageCount })}
            </div>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={!canGoPrev}>
                {t('icons.picker.prevPage')}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setPage((p) => Math.min(pageCount, p + 1))} disabled={!canGoNext}>
                {t('icons.picker.nextPage')}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Drawer>
  )
}
