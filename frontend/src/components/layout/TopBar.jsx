import React, { useMemo, useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ThemeToggle } from '../pickers/ThemeToggle.jsx'
import { LanguagePicker } from '../pickers/LanguagePicker.jsx'
import { getAppConfig } from '../../utils/appConfig.js'
import { getVersion } from '../../api/versionApi.js'

const GITHUB_RELEASES_LATEST = 'https://api.github.com/repos/Dev-CorliJoni/mqtt-ir-module/releases/latest'

function isNewerVersion(candidate, current) {
  const parse = (v) => v.replace(/^v/, '').split('.').map(Number)
  const [ca, cb, cc] = parse(candidate)
  const [ba, bb, bc] = parse(current)
  if (ca !== ba) return ca > ba
  if (cb !== bb) return cb > bb
  return cc > bc
}

function getTitle(pathname, t) {
  if (pathname === '/' || pathname === '') return t('nav.home')
  if (pathname.startsWith('/remotes')) return t('nav.remotes')
  if (pathname === '/agents') return t('nav.agents')
  if (pathname.startsWith('/agent/')) return t('agents.pageTitle')
  if (pathname.startsWith('/settings')) return t('nav.settings')
  return t('app.name')
}

export function TopBar() {
  const { t } = useTranslation()
  const location = useLocation()
  const [updateInfo, setUpdateInfo] = useState(null)

  const appIconSrc = useMemo(() => {
    const { publicBaseUrl } = getAppConfig()
    return `${publicBaseUrl}logos/app-icon-1024.png`
  }, [])

  useEffect(() => {
    let cancelled = false

    async function checkForUpdate() {
      try {
        const [versionData, ghResponse] = await Promise.all([
          getVersion(),
          fetch(GITHUB_RELEASES_LATEST),
        ])
        if (cancelled) return
        if (!versionData?.version) return
        if (!ghResponse.ok) return

        const releaseData = await ghResponse.json()
        if (!releaseData?.tag_name) return

        if (isNewerVersion(releaseData.tag_name, versionData.version)) {
          setUpdateInfo({
            version: releaseData.tag_name.replace(/^v/, ''),
            url: releaseData.html_url,
          })
        }
      } catch {
        // Update check is non-critical; silently ignore any errors.
      }
    }

    checkForUpdate()
    return () => { cancelled = true }
  }, [])

  return (
    <div className="sticky top-0 z-30 border-b border-[rgb(var(--border))] bg-[rgb(var(--card))]">
      <div className="h-14 px-4 md:px-6 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <img
            src={appIconSrc}
            alt=""
            aria-hidden="true"
            className="h-10 w-10 shrink-0 md:hidden"
          />
          <div className="font-semibold text-xl truncate md:hidden">{t('app.name')}</div>
          <div className="font-semibold truncate md:block hidden">{getTitle(location.pathname, t)}</div>
        </div>

        <div className="flex items-center gap-2">
          <ThemeToggle />
          <LanguagePicker />
        </div>
      </div>

      {updateInfo && (
        <div
          className="px-4 py-1.5 flex items-center justify-center gap-2 text-sm border-t"
          style={{
            backgroundColor: 'rgb(var(--warning) / 0.12)',
            borderColor: 'rgb(var(--warning) / 0.4)',
            color: 'rgb(var(--fg))',
          }}
        >
          <span>{t('update.available', { version: updateInfo.version })}</span>
          <a
            href={updateInfo.url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline font-medium"
          >
            {t('update.download')}
          </a>
        </div>
      )}
    </div>
  )
}
