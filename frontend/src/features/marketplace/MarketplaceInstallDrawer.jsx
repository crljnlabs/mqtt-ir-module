import React, { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Drawer } from '../../components/ui/Drawer.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { TextField } from '../../components/ui/TextField.jsx'
import { installMarketplaceRemote } from '../../api/marketplaceApi.js'
import { useToast } from '../../components/ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../../utils/apiErrorMapper.js'

function SignalTypeBadge({ type, protocol }) {
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

export function MarketplaceInstallDrawer({ open, remote, onClose, onSuccess }) {
  const { t } = useTranslation()
  const toast = useToast()
  const errorMapper = new ApiErrorMapper(t)

  const [remoteName, setRemoteName] = useState('')

  useEffect(() => {
    if (!open || !remote) return
    setRemoteName(remote.model || '')
  }, [open, remote])

  const mutation = useMutation({
    mutationFn: () => installMarketplaceRemote({ path: remote.path, remote_name: remoteName.trim() }),
    onSuccess: () => {
      toast.show({ title: t('marketplace.installTitle'), message: t('marketplace.installSuccess') })
      onSuccess?.()
    },
    onError: (e) =>
      toast.show({ title: t('marketplace.installTitle'), message: errorMapper.getMessage(e, 'marketplace.installFailed') }),
  })

  if (!remote) return null

  const buttons = remote.buttons || []

  function handleClose() {
    if (!mutation.isPending) onClose()
  }

  return (
    <Drawer
      open={open}
      title={t('marketplace.installTitle')}
      onClose={handleClose}
      footer={
        <div className="flex gap-2 justify-end">
          <Button variant="secondary" disabled={mutation.isPending} onClick={handleClose}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={!remoteName.trim() || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {t('marketplace.installConfirm')}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <TextField
          label={t('marketplace.remoteNameLabel')}
          value={remoteName}
          onChange={(e) => setRemoteName(e.target.value)}
        />

        {buttons.length > 0 && (
          <div>
            <div className="mb-2 text-sm font-medium">
              {t('marketplace.buttonCount', { count: buttons.length })}
            </div>
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {buttons.map((btn) => (
                <div
                  key={btn.id}
                  className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 bg-[rgb(var(--bg))]"
                >
                  <span className="text-sm truncate">{btn.name}</span>
                  <SignalTypeBadge type={btn.signal_type} protocol={btn.protocol} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Drawer>
  )
}
