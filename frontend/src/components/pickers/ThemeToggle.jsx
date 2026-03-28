import React from 'react'
import Icon from '@mdi/react'
import { mdiThemeLightDark } from '@mdi/js'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getSettings, updateSettings } from '../../api/settingsApi.js'
import { IconButton } from '../ui/IconButton.jsx'
import { Drawer } from '../ui/Drawer.jsx'
import { useTranslation } from 'react-i18next'
import { useToast } from '../ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../../utils/apiErrorMapper.js'

export function ThemeToggle() {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)

  const [open, setOpen] = React.useState(false)

  const settingsQuery = useQuery({ queryKey: ['settings'], queryFn: getSettings })
  const currentTheme = settingsQuery.data?.theme || 'system'

  const updateMutation = useMutation({
    mutationFn: updateSettings,
    onSuccess: (data) => {
      queryClient.setQueryData(['settings'], data)
      toast.show({ title: t('settings.theme'), message: t('common.saved') })
    },
    onError: (e) => toast.show({ title: t('settings.theme'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  const options = [
    { value: 'system', label: t('settings.themeSystem'), valueLabel: t('settings.themeSystemValue') },
    { value: 'light', label: t('settings.themeLight'), valueLabel: t('settings.themeLightValue') },
    { value: 'dark', label: t('settings.themeDark'), valueLabel: t('settings.themeDarkValue') },
  ]

  return (
    <>
      <IconButton label={t('settings.theme')} onClick={() => setOpen(true)}>
        <Icon path={mdiThemeLightDark} size={1} />
      </IconButton>

      <Drawer
        open={open}
        title={t('settings.theme')}
        onClose={() => setOpen(false)}
      >
        <div className="space-y-2">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className={[
                'w-full flex items-center justify-between rounded-xl border px-3 py-3 text-sm font-semibold cursor-pointer transition-colors hover:bg-[rgb(var(--bg))] hover:border-[rgb(var(--primary))]',
                opt.value === currentTheme ? 'border-[rgb(var(--primary))]' : 'border-[rgb(var(--border))]',
              ].join(' ')}
              onClick={() => updateMutation.mutate({ theme: opt.value, language: settingsQuery.data?.language })}
            >
              <span>{opt.label}</span>
              <span className="text-xs text-[rgb(var(--muted))]">{opt.valueLabel}</span>
            </button>
          ))}
        </div>
      </Drawer>
    </>
  )
}
