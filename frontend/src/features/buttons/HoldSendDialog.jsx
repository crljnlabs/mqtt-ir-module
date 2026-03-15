import React, { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Modal } from '../../components/ui/Modal.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { NumberField } from '../../components/ui/NumberField.jsx'

export function HoldSendDialog({ open, buttonName, defaultMs = 1000, onClose, onSend }) {
  const { t } = useTranslation()
  const [holdMs, setHoldMs] = useState(defaultMs)

  useEffect(() => {
    if (!open) {
      // Reset the dialog input when it closes.
      setHoldMs(defaultMs)
      return
    }
    setHoldMs(defaultMs)
  }, [open, defaultMs])

  return (
    <Modal
      open={open}
      title={t('button.holdDialogTitle')}
      onClose={onClose}
      onConfirm={() => { if (!Number.isNaN(Number(holdMs)) && Number(holdMs) > 0) onSend(Number(holdMs)) }}
      footer={
        <div className="flex gap-2 justify-end">
          <Button variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => onSend(Number(holdMs))}
            disabled={Number.isNaN(Number(holdMs)) || Number(holdMs) <= 0}
          >
            {t('button.sendHold')}
          </Button>
        </div>
      }
    >
      <div className="space-y-3">
        <div className="text-sm font-semibold">{buttonName}</div>
        <NumberField
          label={t('button.holdMs')}
          value={holdMs}
          min={0}
          max={5000}
          onChange={(e) => setHoldMs(e.target.value)}
          hint={t('button.holdRangeHint', { min: 0, max: 5000 })}
        />
        <input
          type="range"
          min={0}
          max={5000}
          value={Number(holdMs) || 0}
          onChange={(e) => setHoldMs(e.target.value)}
          className="w-full"
        />
      </div>
    </Modal>
  )
}
