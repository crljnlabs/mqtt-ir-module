import React, { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import Icon from '@mdi/react'
import { mdiRefresh } from '@mdi/js'
import {
  listMarketplace,
  getMarketplaceCategories,
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

  return (
    <div className="rounded-2xl border border-[rgb(var(--border))] bg-[rgb(var(--card))] p-4 flex items-start gap-4">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold">
            {remote.brand} {remote.model !== remote.brand ? remote.model : ''}
          </span>
          <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded bg-[rgb(var(--bg))] border border-[rgb(var(--border))] text-[rgb(var(--muted))]">
            {remote.category}
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
      <div className="flex-shrink-0 flex items-center">
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

  const [q, setQ] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const [category, setCategory] = useState('')
  const [installTarget, setInstallTarget] = useState(null)

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedQ(q), 400)
    return () => clearTimeout(timer)
  }, [q])

  const categoriesQuery = useQuery({
    queryKey: ['marketplace-categories'],
    queryFn: getMarketplaceCategories,
    staleTime: 60_000,
  })

  const listQuery = useQuery({
    queryKey: ['marketplace', debouncedQ, category],
    queryFn: () => listMarketplace({ q: debouncedQ, category }),
    staleTime: 30_000,
  })

  const installedQuery = useQuery({
    queryKey: ['marketplace-installed'],
    queryFn: getInstalledMarketplacePaths,
    staleTime: 30_000,
  })

  const syncStatusQuery = useQuery({
    queryKey: ['marketplace-sync-status'],
    queryFn: getMarketplaceSyncStatus,
    refetchInterval: 5000,
  })

  const syncMutation = useMutation({
    mutationFn: triggerMarketplaceSync,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['marketplace-sync-status'] }),
  })

  const installedPaths = new Set(installedQuery.data || [])
  const items = listQuery.data || []
  const syncStatus = syncStatusQuery.data
  const categories = categoriesQuery.data || []

  const isSyncing = syncStatus?.status === 'running'
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
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-2 sm:items-end">
        <div className="flex-1">
          <TextField
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onClear={() => setQ('')}
            clearLabel={t('common.clear')}
            placeholder={t('marketplace.searchPlaceholder')}
          />
        </div>
        <div className="w-full sm:w-48">
          <SelectField value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">{t('marketplace.categoryAll')}</option>
            {categories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </SelectField>
        </div>
        <a
          href="https://github.com/Lucaslhm/Flipper-IRDB"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-[rgb(var(--primary))] hover:underline self-center whitespace-nowrap"
        >
          {t('marketplace.sourceLink')}
        </a>
      </div>

      <div className="flex items-center gap-3">
        {syncStatus && (
          <span
            className={[
              'text-xs',
              syncStatus.status === 'error' ? 'text-[rgb(var(--danger))]' : 'text-[rgb(var(--muted))]',
            ].join(' ')}
          >
            {formatSyncStatus()}
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
        <div className="grid grid-cols-1 gap-3">
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

      <MarketplaceInstallDrawer
        open={Boolean(installTarget)}
        remote={installTarget}
        onClose={() => setInstallTarget(null)}
        onSuccess={() => {
          setInstallTarget(null)
          queryClient.invalidateQueries({ queryKey: ['remotes'] })
          queryClient.invalidateQueries({ queryKey: ['marketplace-installed'] })
          queryClient.invalidateQueries({ queryKey: ['marketplace', debouncedQ, category] })
        }}
      />
    </div>
  )
}
