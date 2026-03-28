import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Drawer } from '../../components/ui/Drawer.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { TextField } from '../../components/ui/TextField.jsx'

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

export function MarketplaceInstallDrawer({ open, remote, onClose, onInstall }) {
  const { t } = useTranslation()

  const [remoteName, setRemoteName] = useState('')

  useEffect(() => {
    if (!open || !remote) return
    const brand = (remote.brand || '').replace(/_/g, ' ')
    const model = (remote.model || '').replace(/_/g, ' ')
    const brandLower = brand.toLowerCase()
    const modelLower = model.toLowerCase()
    const startsWithBrand = brand && (modelLower === brandLower || modelLower.startsWith(brandLower + ' '))
    setRemoteName(startsWithBrand ? model : brand ? `${brand} ${model}` : model)
  }, [open, remote])

  if (!remote) return null

  const buttons = remote.buttons || []

  function handleConfirm() {
    onInstall({ path: remote.path, remote_name: remoteName.trim() })
    onClose()
  }

  return (
    <Drawer
      open={open}
      title={t('marketplace.installTitle')}
      onClose={onClose}
      footer={
        <div className="flex gap-2 justify-end">
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={!remoteName.trim()}
            onClick={handleConfirm}
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
