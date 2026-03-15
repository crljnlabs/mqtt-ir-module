import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiRefresh, mdiGithub, mdiChevronDown, mdiChevronUp } from '@mdi/js'
import {
  listMarketplace,
  getMarketplaceCategories,
  getMarketplaceBrands,
  getMarketplaceCount,
  getMarketplaceSyncStatus,
  triggerMarketplaceSync,
  getInstalledMarketplacePaths,
} from '../api/marketplaceApi.js'
import { TextField } from '../components/ui/TextField.jsx'
import { Button } from '../components/ui/Button.jsx'
import { SelectField } from '../components/ui/SelectField.jsx'
import { MarketplaceInstallDrawer } from '../features/marketplace/MarketplaceInstallDrawer.jsx'

function SignalBadge({ type, protocol }) {
  if (type === 'parsed') {
    return (
      <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[rgb(var(--primary))] text-[rgb(var(--primary-contrast))]">
        {protocol || 'Protocol'}
      </span>
    )
  }
  return (
    <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[rgb(var(--border))] text-[rgb(var(--muted))]">
      Raw
    </span>
  )
}

function MarketplaceTile({ remote, installed, onInstall }) {
  const { t } = useTranslation()
  const protocols = [
    ...new Set(
      remote.buttons.filter((b) => b.signal_type === 'parsed' && b.protocol).map((b) => b.protocol),
    ),
  ]
  const hasRaw = remote.buttons.some((b) => b.signal_type === 'raw')
  const githubUrl = `https://github.com/Lucaslhm/Flipper-IRDB/blob/main/${remote.path.split('/').map(encodeURIComponent).join('/')}`

  return (
    <div className="rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] p-4 flex items-center gap-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold">
            {remote.brand} {remote.model !== remote.brand ? remote.model : ''}
          </span>
          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[rgb(var(--bg))] border border-[rgb(var(--border))] text-[rgb(var(--muted))]">
            {remote.category.replace(/_/g, ' ')}
          </span>
        </div>
        <div className="mt-1.5 flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-[rgb(var(--muted))]">
            {t('marketplace.buttonCount', { count: remote.buttons.length })}
          </span>
          {hasRaw ? <SignalBadge type="raw" /> : null}
          {protocols.map((p) => (
            <SignalBadge key={p} type="parsed" protocol={p} />
          ))}
        </div>
      </div>
      <div className="flex-shrink-0 flex items-center gap-2">
        <a
          href={githubUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center w-8 h-8 rounded-lg text-[rgb(var(--muted))] hover:text-[rgb(var(--fg))] hover:bg-[rgb(var(--border))] transition-colors"
          title="View on GitHub"
        >
          <Icon path={mdiGithub} size={0.85} />
        </a>
        {installed ? (
          <span className="text-xs font-semibold text-[rgb(var(--primary))]">
            ✓ {t('marketplace.installedBadge')}
          </span>
        ) : (
          <Button size="sm" onClick={() => onInstall(remote)}>
            {t('marketplace.installButton')}
          </Button>
        )}
      </div>
    </div>
  )
}

export function MarketplacePage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const prevSyncStatusRef = useRef(null)

  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [category, setCategory] = useState('')
  const [brand, setBrand] = useState('')
  const [installTarget, setInstallTarget] = useState(null)
  const [filtersOpen, setFiltersOpen] = useState(false)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 400)
    return () => clearTimeout(timer)
  }, [q])

const syncStatusQuery = useQuery({
    queryKey: ['marketplace-sync-status'],
    queryFn: getMarketplaceSyncStatus,
    refetchInterval: 5000,
  })

  const syncStatus = syncStatusQuery.data
  const isSyncing = syncStatus?.status === 'running'

  // Invalidate all data queries the moment sync transitions running → idle
  useEffect(() => {
    const current = syncStatus?.status
    const prev = prevSyncStatusRef.current
    prevSyncStatusRef.current = current
    if (prev === 'running' && current === 'idle') {
      queryClient.invalidateQueries({ queryKey: ['marketplace'] })
      queryClient.invalidateQueries({ queryKey: ['marketplace-categories'] })
      queryClient.invalidateQueries({ queryKey: ['marketplace-brands'] })
      queryClient.invalidateQueries({ queryKey: ['marketplace-count'] })
      queryClient.invalidateQueries({ queryKey: ['marketplace-installed'] })
    }
  }, [syncStatus?.status, queryClient])

  const categoriesQuery = useQuery({
    queryKey: ['marketplace-categories'],
    queryFn: getMarketplaceCategories,
    staleTime: 60_000,
    refetchInterval: isSyncing ? 4000 : false,
  })

  const brandsQuery = useQuery({
    queryKey: ['marketplace-brands', category],
    queryFn: () => getMarketplaceBrands(category),
    staleTime: 60_000,
    refetchInterval: isSyncing ? 4000 : false,
  })

  const countQuery = useQuery({
    queryKey: ['marketplace-count'],
    queryFn: getMarketplaceCount,
    staleTime: 60_000,
    refetchInterval: isSyncing ? 4000 : false,
  })

  const listQuery = useQuery({
    queryKey: ['marketplace', debouncedQ, category, brand],
    queryFn: () => listMarketplace({ q: debouncedQ, category, brand }),
    staleTime: 30_000,
    refetchInterval: isSyncing ? 4000 : false,
  })

  const installedQuery = useQuery({
    queryKey: ['marketplace-installed'],
    queryFn: getInstalledMarketplacePaths,
    staleTime: 30_000,
  })

  const syncMutation = useMutation({
    mutationFn: triggerMarketplaceSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['marketplace-sync-status'] }),
  })

  const installedPaths = new Set(installedQuery.data || [])
  const items = listQuery.data || []
  const categories = Array.isArray(categoriesQuery.data) ? categoriesQuery.data : []
  const brands = Array.isArray(brandsQuery.data) ? brandsQuery.data : []
  const totalCount = typeof countQuery.data?.total === 'number' ? countQuery.data.total : null

  const neverSynced = !isSyncing && !syncStatus?.last_synced

  function formatSyncStatus() {
    if (!syncStatus) return null
    if (isSyncing) {
      return `${t('marketplace.syncRunning')} (${syncStatus.done ?? 0}/${syncStatus.total ?? '?'})`
    }
    if (syncStatus.status === 'error') {
      return `${t('marketplace.syncError')}: ${syncStatus.error}`
    }
    if (syncStatus.last_synced) {
      return t('marketplace.syncLastAt', {
        when: new Date(syncStatus.last_synced * 1000).toLocaleString(),
      })
    }
    return t('marketplace.syncNever')
  }

  return (
    <div className="h-full flex flex-col">
      <div className="flex flex-col gap-2 pb-3 border-b border-[rgb(var(--border))]">
        <div className="flex items-center gap-2">
          <div className="flex-1">
            <TextField
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onClear={() => setQ('')}
              clearLabel={t('common.clear')}
              placeholder={t('marketplace.searchPlaceholder')}
            />
          </div>
          <button
            type="button"
            onClick={() => setFiltersOpen((v) => !v)}
            className="shrink-0 flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs text-[rgb(var(--muted))] border border-[rgb(var(--border))] hover:bg-[rgb(var(--border))] transition-colors"
            aria-expanded={filtersOpen}
          >
            <Icon path={filtersOpen ? mdiChevronUp : mdiChevronDown} size={0.75} />
          </button>
        </div>

        {filtersOpen && (
          <>
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="flex-1">
                <SelectField
                  value={brand}
                  onChange={(e) => setBrand(e.target.value)}
                  searchable
                  searchPlaceholder={t('marketplace.brandSearch')}
                >
                  <option value="">{t('marketplace.brandAll')}</option>
                  {brands.map((b) => (
                    <option key={b} value={b}>{b.replace(/_/g, ' ')}</option>
                  ))}
                </SelectField>
              </div>
              <div className="flex-1">
                <SelectField
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  searchable
                  searchPlaceholder={t('marketplace.categorySearch')}
                >
                  <option value="">{t('marketplace.categoryAll')}</option>
                  {categories.map((cat) => (
                    <option key={cat} value={cat}>
                      {cat.replace(/_/g, ' ')}
                    </option>
                  ))}
                </SelectField>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {syncStatus && (
                <span
                  className={[
                    'text-xs flex-1 min-w-0 truncate',
                    syncStatus.status === 'error' ? 'text-[rgb(var(--danger))]' : 'text-[rgb(var(--muted))]',
                  ].join(' ')}
                >
                  {formatSyncStatus()}
                  {totalCount !== null && !isSyncing && syncStatus.last_synced
                    ? ` · ${totalCount} ${t('marketplace.totalRemotes')}`
                    : null}
                </span>
              )}
              <Button
                size="sm"
                variant="secondary"
                disabled={isSyncing || syncMutation.isPending}
                onClick={() => syncMutation.mutate()}
              >
                <Icon path={mdiRefresh} size={0.75} />
                {t('marketplace.syncButton')}
              </Button>
            </div>
          </>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto pt-3">
        {neverSynced && !listQuery.isFetching ? (
          <div className="text-sm text-[rgb(var(--muted))] py-12 text-center space-y-3">
            <p>{t('marketplace.syncNever')}</p>
            <Button
              variant="secondary"
              disabled={isSyncing || syncMutation.isPending}
              onClick={() => syncMutation.mutate()}
            >
              <Icon path={mdiRefresh} size={0.85} />
              {t('marketplace.syncButton')}
            </Button>
          </div>
        ) : items.length === 0 && !listQuery.isFetching ? (
          <p className="text-sm text-[rgb(var(--muted))] py-8 text-center">{t('marketplace.noResults')}</p>
        ) : (
          <div className="grid grid-cols-1 gap-3 pb-3">
            {items.map((remote) => (
              <MarketplaceTile
                key={remote.id}
                remote={remote}
                installed={installedPaths.has(remote.path)}
                onInstall={setInstallTarget}
              />
            ))}
          </div>
        )}
      </div>

      <MarketplaceInstallDrawer
        open={Boolean(installTarget)}
        remote={installTarget}
        onClose={() => setInstallTarget(null)}
        onSuccess={() => {
          setInstallTarget(null)
          queryClient.invalidateQueries({ queryKey: ['remotes'] })
          queryClient.invalidateQueries({ queryKey: ['marketplace-installed'] })
          queryClient.invalidateQueries({ queryKey: ['marketplace', debouncedQ, category, brand] })
        }}
      />
    </div>
  )
}

