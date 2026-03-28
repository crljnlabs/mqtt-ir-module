import React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getSettings, updateSettings } from '../../api/settingsApi.js'
import { IconButton } from '../ui/IconButton.jsx'
import { Drawer } from '../ui/Drawer.jsx'
import { useToast } from '../ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../../utils/apiErrorMapper.js'

const LANGUAGES = [
  { code: 'en', labelKey: 'languages.en', flag: '🇬🇧' },
  { code: 'de', labelKey: 'languages.de', flag: '🇩🇪' },
  { code: 'es', labelKey: 'languages.es', flag: '🇪🇸' },
  { code: 'pt-PT', labelKey: 'languages.pt-PT', flag: '🇵🇹' },
  { code: 'fr', labelKey: 'languages.fr', flag: '🇫🇷' },
  { code: 'zh-CN', labelKey: 'languages.zh-CN', flag: '🇨🇳' },
  { code: 'hi', labelKey: 'languages.hi', flag: '🇮🇳' },
  { code: 'ru', labelKey: 'languages.ru', flag: '🇷🇺' },
  { code: 'ar', labelKey: 'languages.ar', flag: '🇸🇦' },
  { code: 'bn', labelKey: 'languages.bn', flag: '🇧🇩' },
  { code: 'id', labelKey: 'languages.id', flag: '🇮🇩' },
  { code: 'ur', labelKey: 'languages.ur', flag: '🇵🇰' },
  { code: 'ja', labelKey: 'languages.ja', flag: '🇯🇵' },
]

export function LanguagePicker() {
  const { t, i18n } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)

  const [open, setOpen] = React.useState(false)

  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: getSettings })
  const current = settingsQuery.data?.language || 'en'
  const currentMeta = LANGUAGES.find((l) => l.code === current) || LANGUAGES[0]

  const updateMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      const tNew = i18n.getFixedT(data.language)
      toast.show({ title: tNew('settings.language'), message: tNew('common.saved') })
    },
    onError: (e) => toast.show({ title: t('settings.language'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  return (
    <>
      <IconButton label={t('settings.language')} onClick={() => setOpen(true)}>
        <span className="text-lg">{currentMeta.flag}</span>
      </IconButton>

      <Drawer
        open={open}
        title={t('settings.language')}
        onClose={() => setOpen(false)}
      >
        <div className="space-y-2">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              type="button"
              className={[
                'w-full flex items-center justify-between rounded-xl border px-3 py-3 text-sm font-semibold cursor-pointer transition-colors hover:bg-[rgb(var(--bg))] hover:border-[rgb(var(--primary))]',
                lang.code === current ? 'border-[rgb(var(--primary))]' : 'border-[rgb(var(--border))]',
              ].join(' ')}
              onClick={() => {
                updateMutation.mutate({ language: lang.code, theme: settingsQuery.data?.theme })
              }}
            >
              <span className="flex items-center gap-3">
                <span className="text-lg">{lang.flag}</span>
                <span>{t(lang.labelKey)}</span>
              </span>
              <span className="text-xs text-[rgb(var(--muted))]">{lang.code}</span>
            </button>
          ))}
        </div>
      </Drawer>
    </>
  )
}
