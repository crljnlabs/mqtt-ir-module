import React, { useEffect, useState } from 'react'
import Icon from '@mdi/react'
import { mdiTrashCanOutline } from '@mdi/js'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Drawer } from '../../components/ui/Drawer.jsx'
import { Button } from '../../components/ui/Button.jsx'
import { NumberField } from '../../components/ui/NumberField.jsx'
import { Collapse } from '../../components/ui/Collapse.jsx'
import { SelectField } from '../../components/ui/SelectField.jsx'
import { EntityEditHeader } from '../../components/ui/EntityEditHeader.jsx'
import { IconPicker } from '../../components/pickers/IconPicker.jsx'
import { listAgents } from '../../api/agentsApi.js'
import { updateRemote } from '../../api/remotesApi.js'
import { DEFAULT_REMOTE_ICON } from '../../icons/iconRegistry.js'
import { useToast } from '../../components/ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../../utils/apiErrorMapper.js'

export function RemoteEditorDrawer({ open, remote, onClose, onDelete }) {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)

  const [name, setName] = useState('')
  const [icon, setIcon] = useState(null)
  const [carrierHz, setCarrierHz] = useState('')
  const [dutyCycle, setDutyCycle] = useState('')
  const [assignedAgentId, setAssignedAgentId] = useState('')
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [iconPickerOpen, setIconPickerOpen] = useState(false)
  const agentsQuery = useQuery({ queryKey: ['agents'], queryFn: listAgents, staleTime: 30_000 })
  const agents = agentsQuery.data || []

  useEffect(() => {
    if (!open) {
      // Reset form state when the drawer closes to avoid stale edits.
      setName('')
      setIcon(null)
      setCarrierHz('')
      setDutyCycle('')
      setAssignedAgentId('')
      setAdvancedOpen(false)
      setIconPickerOpen(false)
      return
    }
    if (!remote) return
    setName(remote.name || '')
    setIcon(remote.icon ?? null)
    setCarrierHz(remote.carrier_hz ?? '')
    setDutyCycle(remote.duty_cycle ?? '')
    setAssignedAgentId(remote.assigned_agent_id ?? '')
    setAdvancedOpen(false)
  }, [open, remote])

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = {
        ...remote,
        name: name.trim(),
        icon: icon ?? null,
        carrier_hz: carrierHz === '' ? null : Number(carrierHz),
        duty_cycle: dutyCycle === '' ? null : Number(dutyCycle),
        assigned_agent_id: assignedAgentId ? assignedAgentId : null,
      }
      return updateRemote(remote.id, payload)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      queryClient.invalidateQueries({ queryKey: ['buttons', remote.id] })
      onClose()
    },
    onError: (e) => toast.show({ title: t('remote.title'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  function handleClose() {
    if (mutation.isPending) return
    if (!name.trim()) { onClose(); return }
    mutation.mutate()
  }

  if (!remote) return null

  const hasAgents = agents.length > 0
  const allowUnassigned = !remote.assigned_agent_id || (agentsQuery.isSuccess && !hasAgents)
  const assignedExists = assignedAgentId && agents.some((agent) => agent.agent_id === assignedAgentId)
  const sortedAgents = [...agents].sort((a, b) => {
    if (a.status === b.status) return (a.name || a.agent_id).localeCompare(b.name || b.agent_id)
    if (a.status === 'online') return -1
    if (b.status === 'online') return 1
    return (a.name || a.agent_id).localeCompare(b.name || b.agent_id)
  })

  return (
    <>
      <Drawer
        open={open}
        title={`${t('common.edit')} ${t('remote.title')}`}
        onClose={handleClose}
      >
        <div className="space-y-4">
          <EntityEditHeader
            label={t('remotes.name')}
            name={name}
            onNameChange={(e) => setName(e.target.value)}
            onIconClick={() => setIconPickerOpen(true)}
          />

          <SelectField
            label={t('agents.remoteLabel')}
            hint={t('agents.remoteHint')}
            value={assignedAgentId || ''}
            onChange={(event) => setAssignedAgentId(event.target.value)}
          >
            {allowUnassigned ? <option value="">{t('agents.unassigned')}</option> : null}
            {!assignedExists && assignedAgentId ? (
              <option value={assignedAgentId}>{t('agents.unknownAgent', { id: assignedAgentId })}</option>
            ) : null}
            {sortedAgents.map((agent) => {
              const label = agent.name || agent.agent_id
              const statusLabel = agent.status === 'online' ? '' : ` (${t('agents.statusOffline')})`
              return (
                <option key={agent.agent_id} value={agent.agent_id}>
                  {label}{statusLabel}
                </option>
              )
            })}
          </SelectField>

          <Collapse open={advancedOpen} onToggle={() => setAdvancedOpen((v) => !v)} title={t('common.advanced')}>
            <div className="grid grid-cols-1 gap-3">
              <NumberField
                label={t('remote.carrierHzLabel')}
                hint={t('remote.carrierHzHint')}
                value={carrierHz}
                onChange={(e) => setCarrierHz(e.target.value)}
                placeholder="38000"
              />
              <NumberField
                label={t('remote.dutyCycleLabel')}
                hint={t('remote.dutyCycleHint')}
                value={dutyCycle}
                onChange={(e) => setDutyCycle(e.target.value)}
                placeholder="33"
              />
            </div>
          </Collapse>

          {onDelete ? (
            <>
              <hr className="border-[rgb(var(--border))]" />
              <Button
                variant="danger"
                className="w-full justify-start"
                disabled={mutation.isPending}
                onClick={() => { onClose(); onDelete(remote) }}
              >
                <Icon path={mdiTrashCanOutline} size={1} />
                {t('common.delete')}
              </Button>
            </>
          ) : null}
        </div>
      </Drawer>

      <IconPicker
        open={iconPickerOpen}
        title={t('remote.iconTitle')}
        initialIconKey={icon || DEFAULT_REMOTE_ICON}
        onClose={() => setIconPickerOpen(false)}
        onBack={() => setIconPickerOpen(false)}
        onSelect={(key) => {
          setIcon(key)
          setIconPickerOpen(false)
        }}
      />
    </>
  )
}
