import React, { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { listRemotes, createRemote, deleteRemote } from '../api/remotesApi.js'
import { RemoteTile } from '../features/remotes/RemoteTile.jsx'
import { TextField } from '../components/ui/TextField.jsx'
import { Button } from '../components/ui/Button.jsx'
import { Modal } from '../components/ui/Modal.jsx'
import { ConfirmDialog } from '../components/ui/ConfirmDialog.jsx'
import { RemoteEditorDrawer } from '../features/remotes/RemoteEditorDrawer.jsx'
import { useToast } from '../components/ui/ToastProvider.jsx'
import { ApiErrorMapper } from '../utils/apiErrorMapper.js'

export function RemotesPage() {
  const { t } = useTranslation()
  const toast = useToast()
  const queryClient = useQueryClient()
  const errorMapper = new ApiErrorMapper(t)

  const remotesQuery = useQuery({ queryKey: ['remotes'], queryFn: listRemotes })

  const [query, setQuery] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [newName, setNewName] = useState('')

  const [editRemote, setEditRemote] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)

  const handleCreateClose = () => {
    // Reset the create modal input when it closes.
    setCreateOpen(false)
    setNewName('')
  }

  // Normalize the query so search behaves consistently across different inputs.
  const filtered = useMemo(() => {
    const list = remotesQuery.data || []
    const q = query.trim().toLowerCase()
    if (!q) return list
    return list.filter((r) => (r.name || '').toLowerCase().includes(q))
  }, [remotesQuery.data, query])

  const createMutation = useMutation({
    mutationFn: () => createRemote({ name: newName.trim(), icon: null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('remotes.create'), message: t('common.saved') })
      handleCreateClose()
    },
    onError: (e) => toast.show({ title: t('remotes.create'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id) => deleteRemote(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['remotes'] })
      toast.show({ title: t('common.delete'), message: t('common.deleted') })
      setDeleteTarget(null)
    },
    onError: (e) => toast.show({ title: t('common.delete'), message: errorMapper.getMessage(e, 'common.failed') }),
  })

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-2 sm:items-end sm:justify-between">
        <div className="flex-1">
          <TextField
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onClear={() => setQuery('')}
            clearLabel={t('common.clear')}
            placeholder={t('common.search')}
          />
        </div>
        <Button onClick={() => setCreateOpen(true)}>{t('remotes.create')}</Button>
      </div>

      <div className="grid grid-cols-1 gap-3">
        {filtered.map((remote) => (
          <RemoteTile
            key={remote.id}
            remote={remote}
            onEdit={(r) => setEditRemote(r)}
            onDelete={(r) => setDeleteTarget(r)}
          />
        ))}
      </div>

      <RemoteEditorDrawer open={Boolean(editRemote)} remote={editRemote} onClose={() => setEditRemote(null)} />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={t('remotes.deleteConfirmTitle')}
        body={t('remotes.deleteConfirmBody')}
        confirmText={t('common.delete')}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => deleteMutation.mutate(deleteTarget.id)}
      />

      <Modal
        open={createOpen}
        title={t('remotes.create')}
        onClose={handleCreateClose}
        onConfirm={() => { if (newName.trim() && !createMutation.isPending) createMutation.mutate() }}
        footer={
          <div className="flex gap-2 justify-end">
            <Button variant="secondary" onClick={handleCreateClose}>
              {t('common.cancel')}
            </Button>
            <Button onClick={() => createMutation.mutate()} disabled={!newName.trim() || createMutation.isPending}>
              {t('common.save')}
            </Button>
          </div>
        }
      >
        <TextField label={t('remotes.name')} value={newName} onChange={(e) => setNewName(e.target.value)} />
      </Modal>
    </div>
  )
}
