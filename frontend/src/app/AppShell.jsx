import React, { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import i18n from 'i18next'
import { useTranslation } from 'react-i18next'

import { getHealth } from '../api/healthApi.js'
import { getSettings } from '../api/settingsApi.js'
import { BottomNav } from '../components/layout/BottomNav.jsx'
import { SidebarNav } from '../components/layout/SidebarNav.jsx'
import { TopBar } from '../components/layout/TopBar.jsx'
import { Modal } from '../components/ui/Modal.jsx'
import { Button } from '../components/ui/Button.jsx'
import { applyTheme } from '../features/settings/theme.js'
import { useToast } from '../components/ui/ToastProvider.jsx'
import { ErrorCallout } from '../components/ui/ErrorCallout.jsx'

export function AppShell() {
  const { t } = useTranslation()
  const toast = useToast()

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchInterval: 300000,
  })

  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
    staleTime: 60_000,
  })

  const language = settingsQuery.data?.language
  const [offlineOpen, setOfflineOpen] = useState(false)

  useEffect(() => {
    if (healthQuery.isError) setOfflineOpen(true)
  }, [healthQuery.isError])

  useEffect(() => {
    const theme = settingsQuery.data?.theme || 'system'
    applyTheme(theme)
  }, [settingsQuery.data?.theme])

  useEffect(() => {
    if (!language) return
    const currentLanguage = i18n.resolvedLanguage || i18n.language
    if (currentLanguage === language) {
      document.documentElement.lang = language
      return
    }
    i18n.changeLanguage(language).catch(() => {
      toast.show({
        title: i18n.t('settings.language'),
        message: i18n.t('settings.languageChangeFailed'),
      })
    })
    document.documentElement.lang = language
  }, [language, toast])

  return (
    <div className="h-dvh overflow-hidden">
      <SidebarNav />
      <div className="md:pl-64 h-full flex flex-col overflow-hidden">
        <TopBar />

        <main className="flex-1 overflow-y-auto px-4 md:px-6 pb-24 md:pb-4 pt-4">
          <Outlet />
        </main>

        <BottomNav />
      </div>

      <Modal
        open={offlineOpen}
        title={t('errors.offlineTitle')}
        onClose={() => setOfflineOpen(false)}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={() => setOfflineOpen(false)}>
              {t('common.close')}
            </Button>
            <Button
              onClick={() => {
                healthQuery.refetch()
                settingsQuery.refetch()
              }}
            >
              {t('common.retry')}
            </Button>
          </div>
        }
      >
        <div className="space-y-3">
          <p className="text-sm text-[rgb(var(--muted))]">{t('errors.offlineBody')}</p>
          {healthQuery.error ? <ErrorCallout error={healthQuery.error} /> : null}
        </div>
      </Modal>
    </div>
  )
}
