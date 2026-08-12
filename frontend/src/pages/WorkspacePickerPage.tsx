import React, { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Workspace, listWorkspaces, switchWorkspace, createWorkspace } from '../lib/api'

export default function WorkspacePickerPage() {
  const navigate = useNavigate()
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(true)
  const [showNewInput, setShowNewInput] = useState(false)
  const [newWsName, setNewWsName] = useState('')
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    listWorkspaces().then((list) => {
      setWorkspaces(list)
      setLoading(false)
    })
  }, [])

  const handleSelect = async (wsId: string) => {
    setLoading(true)
    const success = await switchWorkspace(wsId)
    if (success) {
      navigate('/')
    } else {
      setLoading(false)
    }
  }

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newWsName.trim()) return
    setCreating(true)
    const res = await createWorkspace(newWsName.trim())
    setCreating(false)
    if (res) {
      navigate('/')
    }
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--bg-base)',
      color: 'var(--text-primary)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      padding: 16,
      fontFamily: "'Inter', system-ui, sans-serif",
    }}>
      <div style={{ maxWidth: 460, width: '100%' }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 52,
            height: 52,
            borderRadius: 'var(--radius-md)',
            background: 'var(--accent-dim)',
            border: '1px solid var(--border-focus)',
            color: 'var(--accent-light)',
            fontSize: 24,
            marginBottom: 16,
          }}>
            🏢
          </div>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
            Choose a Workspace
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 6, margin: 0 }}>
            Select the workspace you want to enter, or create a new one.
          </p>
        </div>

        {loading ? (
          <div style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            padding: 32,
            textAlign: 'center',
            fontSize: 13,
            color: 'var(--text-muted)',
          }}>
            Loading workspaces...
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 24 }}>
            {workspaces.map((ws) => (
              <button
                key={ws.id}
                type="button"
                onClick={() => handleSelect(ws.id)}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  padding: '16px 20px',
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius-lg)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  boxSizing: 'border-box',
                }}
              >
                <div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {ws.name}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4, display: 'flex', gap: 12 }}>
                    <span>Role: {ws.role || 'Owner'}</span>
                    {ws.account_count !== undefined && (
                      <span>• {ws.account_count} connected account{ws.account_count !== 1 ? 's' : ''}</span>
                    )}
                  </div>
                </div>

                <div style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: 'var(--bg-glass)',
                  color: 'var(--accent-light)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 14,
                }}>
                  ➔
                </div>
              </button>
            ))}

            {showNewInput ? (
              <form
                onSubmit={handleCreate}
                style={{
                  padding: 20,
                  background: 'var(--bg-surface)',
                  border: '1px solid var(--border-focus)',
                  borderRadius: 'var(--radius-lg)',
                }}
              >
                <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
                  Workspace Name
                </label>
                <input
                  type="text"
                  value={newWsName}
                  onChange={(e) => setNewWsName(e.target.value)}
                  placeholder="e.g. Work, Personal"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    background: 'var(--bg-base)',
                    border: '1px solid var(--border)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: 13,
                    color: 'var(--text-primary)',
                    marginBottom: 14,
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                  autoFocus
                />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button
                    type="button"
                    onClick={() => setShowNewInput(false)}
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: 12 }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creating || !newWsName.trim()}
                    className="btn btn-primary btn-sm"
                    style={{ fontSize: 12 }}
                  >
                    {creating ? 'Creating...' : 'Create & Enter'}
                  </button>
                </div>
              </form>
            ) : (
              <button
                type="button"
                onClick={() => setShowNewInput(true)}
                style={{
                  width: '100%',
                  padding: '14px 20px',
                  background: 'transparent',
                  border: '1px dashed var(--border)',
                  borderRadius: 'var(--radius-lg)',
                  fontSize: 13,
                  fontWeight: 500,
                  color: 'var(--accent-light)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                ➕ Create New Workspace
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
