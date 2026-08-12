import React, { useState, useEffect } from 'react'
import { Workspace, listWorkspaces, switchWorkspace, createWorkspace, deleteWorkspace } from '../lib/api'

interface WorkspaceSwitcherProps {
  currentWorkspaceId: string
  currentWorkspaceName: string
  onWorkspaceSwitched?: () => void
}

export default function WorkspaceSwitcher({
  currentWorkspaceId,
  currentWorkspaceName,
  onWorkspaceSwitched,
}: WorkspaceSwitcherProps) {
  const [open, setOpen] = useState(false)
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [loading, setLoading] = useState(false)
  const [showNewModal, setShowNewModal] = useState(false)
  const [newWsName, setNewWsName] = useState('')
  const [creating, setCreating] = useState(false)
  const [deletingWs, setDeletingWs] = useState<{ id: string; name: string } | null>(null)
  const [isDeletingWs, setIsDeletingWs] = useState(false)

  const fetchList = async () => {
    setLoading(true)
    const list = await listWorkspaces()
    setWorkspaces(list)
    setLoading(false)
  }

  useEffect(() => {
    if (open) {
      fetchList()
    }
  }, [open])

  const handleSwitch = async (id: string) => {
    if (id === currentWorkspaceId) {
      setOpen(false)
      return
    }
    setLoading(true)
    const success = await switchWorkspace(id)
    if (success) {
      setOpen(false)
      if (onWorkspaceSwitched) {
        onWorkspaceSwitched()
      } else {
        window.location.reload()
      }
    } else {
      setLoading(false)
    }
  }

  const handleExitWorkspace = async (e: React.MouseEvent) => {
    e.stopPropagation()
    setLoading(true)
    const success = await switchWorkspace(null as any)
    if (success) {
      setOpen(false)
      if (onWorkspaceSwitched) {
        onWorkspaceSwitched()
      } else {
        window.location.reload()
      }
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
      setShowNewModal(false)
      setNewWsName('')
      setOpen(false)
      window.location.reload()
    }
  }

  return (
    <div style={{ position: 'relative', width: '100%' }}>
      {/* Trigger Button */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        style={{
          width: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          fontSize: '12px',
          fontWeight: 500,
          color: 'var(--text-primary)',
          background: 'rgba(255, 255, 255, 0.04)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-md)',
          cursor: 'pointer',
          transition: 'all 0.15s ease',
          boxSizing: 'border-box',
        }}
        title="Switch active workspace"
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0, overflow: 'hidden' }}>
          <div
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: currentWorkspaceId ? '#34d399' : '#9ca3af',
              flexShrink: 0,
            }}
          />
          <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', fontWeight: 600, color: 'var(--text-primary)' }}>
            {currentWorkspaceName || 'Select Workspace'}
          </span>
        </div>

        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            flexShrink: 0,
            marginLeft: 6,
            color: 'var(--text-secondary)',
            transform: open ? 'rotate(180deg)' : 'none',
            transition: 'transform 0.2s ease',
          }}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>

      {/* Dropdown Menu */}
      {open && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 998 }}
            onClick={() => setOpen(false)}
          />
          <div
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: '100%',
              marginBottom: 8,
              zIndex: 999,
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)',
              boxShadow: 'var(--shadow-lg)',
              overflow: 'hidden',
              padding: '6px 0',
              minWidth: 200,
            }}
          >
            <div
              style={{
                padding: '6px 12px',
                fontSize: 10,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.6px',
                color: 'var(--text-muted)',
                borderBottom: '1px solid var(--border)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span>Workspaces</span>
              {currentWorkspaceId && (
                <button
                  type="button"
                  title="Exit active workspace (Switch to Single Account Mode)"
                  onClick={handleExitWorkspace}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 20,
                    height: 20,
                    borderRadius: 'var(--radius-sm)',
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--text-muted)',
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = '#f87171'
                    e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'
                    e.currentTarget.style.boxShadow = '0 0 10px rgba(239, 68, 68, 0.45)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = 'var(--text-muted)'
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.boxShadow = 'none'
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                    <polyline points="16 17 21 12 16 7" />
                    <line x1="21" y1="12" x2="9" y2="12" />
                  </svg>
                </button>
              )}
            </div>

            <div style={{ maxHeight: 180, overflowY: 'auto', padding: '4px 0' }}>
              {loading && workspaces.length === 0 ? (
                <div style={{ padding: '8px 12px', fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic', textAlign: 'center' }}>
                  Loading...
                </div>
              ) : (
                workspaces.map((ws) => {
                  const isCurrent = ws.id === currentWorkspaceId
                  return (
                    <div
                      key={ws.id}
                      onClick={() => handleSwitch(ws.id)}
                      style={{
                        width: '100%',
                        textAlign: 'left',
                        padding: '8px 12px',
                        fontSize: 12,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        background: isCurrent ? 'rgba(99, 102, 241, 0.15)' : 'transparent',
                        color: isCurrent ? 'var(--accent-light)' : 'var(--text-primary)',
                        fontWeight: isCurrent ? 600 : 400,
                        border: 'none',
                        cursor: 'pointer',
                        transition: 'background 0.15s ease',
                        boxSizing: 'border-box',
                      }}
                    >
                      <div style={{ minWidth: 0, overflow: 'hidden', paddingRight: 8 }}>
                        <div style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{ws.name}</div>
                        {ws.account_count !== undefined && (
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
                            {ws.account_count} account{ws.account_count !== 1 ? 's' : ''}
                          </div>
                        )}
                      </div>
                      
                      <button
                        type="button"
                        title={`Delete workspace "${ws.name}"`}
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeletingWs({ id: ws.id, name: ws.name })
                        }}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: 22,
                          height: 22,
                          borderRadius: 'var(--radius-sm)',
                          background: 'transparent',
                          border: 'none',
                          color: 'var(--text-muted)',
                          cursor: 'pointer',
                          opacity: 0.6,
                          transition: 'all 0.2s ease',
                          flexShrink: 0,
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.opacity = '1'
                          e.currentTarget.style.color = '#ef4444'
                          e.currentTarget.style.background = 'rgba(239, 68, 68, 0.2)'
                          e.currentTarget.style.boxShadow = '0 0 10px rgba(239, 68, 68, 0.45)'
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.opacity = '0.6'
                          e.currentTarget.style.color = 'var(--text-muted)'
                          e.currentTarget.style.background = 'transparent'
                          e.currentTarget.style.boxShadow = 'none'
                        }}
                      >
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                        </svg>
                      </button>
                    </div>
                  )
                })
              )}
            </div>

            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 4, marginTop: 4, paddingLeft: 4, paddingRight: 4 }}>
              <button
                type="button"
                onClick={() => setShowNewModal(true)}
                style={{
                  width: '100%',
                  textAlign: 'left',
                  padding: '6px 10px',
                  fontSize: 12,
                  color: 'var(--accent-light)',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontWeight: 500,
                }}
              >
                <span style={{ fontSize: 14 }}>➕</span>
                Create Workspace
              </button>
            </div>
          </div>
        </>
      )}

      {/* Create Workspace Modal — Image 1 Style */}
      {showNewModal && (
        <div className="profile-modal-overlay" onClick={() => setShowNewModal(false)}>
          <div
            className="profile-modal-card"
            style={{ maxWidth: 440, width: '92vw', padding: '24px', boxSizing: 'border-box' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: '12px',
                  background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.25), rgba(168, 85, 247, 0.25))',
                  border: '1px solid rgba(99, 102, 241, 0.4)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: '#a5b4fc',
                  flexShrink: 0,
                }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
                    <path d="M19 21V5a2 2 0 0 0-2-2H7a2 2 0 0 0-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5m0 0v-5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v5m-4 0h4" />
                  </svg>
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: 17, fontWeight: 600, color: 'var(--text-primary)' }}>
                    Create Workspace
                  </h3>
                  <p style={{ margin: '3px 0 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                    Organize isolated email accounts and chat history
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="btn-icon"
                onClick={() => setShowNewModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18, padding: 4 }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreate} style={{ marginTop: 18 }}>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)', marginBottom: 8 }}>
                Workspace Name
              </label>
              <input
                type="text"
                autoFocus
                placeholder="e.g. Work, Side Hustle, Client Projects"
                value={newWsName}
                onChange={(e) => setNewWsName(e.target.value)}
                style={{
                  width: '100%',
                  padding: '11px 14px',
                  borderRadius: 'var(--radius-md)',
                  background: 'rgba(255, 255, 255, 0.05)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                  fontSize: 14,
                  outline: 'none',
                  boxSizing: 'border-box',
                  transition: 'all 0.2s ease',
                }}
                onFocus={(e) => e.target.style.borderColor = 'var(--accent)'}
                onBlur={(e) => e.target.style.borderColor = 'var(--border)'}
              />

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 22 }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowNewModal(false)}
                  disabled={creating}
                  style={{ minHeight: 38 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={creating || !newWsName.trim()}
                  style={{
                    minHeight: 38,
                    background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                    boxShadow: '0 0 16px rgba(99, 102, 241, 0.4)',
                    color: '#ffffff',
                    fontWeight: 600,
                  }}
                >
                  {creating ? 'Creating...' : 'Create Workspace'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
      {/* Delete Workspace Confirmation Modal */}
      {deletingWs && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 10000,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: 16,
          }}
          onClick={() => setDeletingWs(null)}
        >
          <div
            style={{
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius-lg)',
              padding: 24,
              maxWidth: 420,
              width: '100%',
              boxShadow: 'var(--shadow-lg)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div style={{
                width: 40,
                height: 40,
                borderRadius: '10px',
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#ef4444',
                flexShrink: 0,
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                </svg>
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>
                  Delete Workspace?
                </h3>
                <p style={{ margin: '2px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                  This action cannot be undone.
                </p>
              </div>
            </div>

            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 20 }}>
              Are you sure you want to permanently delete workspace <strong style={{ color: 'var(--text-primary)' }}>"{deletingWs.name}"</strong>? All accounts connected inside this workspace and its chat history will be permanently deleted.
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setDeletingWs(null)}
                disabled={isDeletingWs}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                disabled={isDeletingWs}
                onClick={async () => {
                  setIsDeletingWs(true)
                  await deleteWorkspace(deletingWs.id)
                  setIsDeletingWs(false)
                  setDeletingWs(null)
                  setOpen(false)
                  if (onWorkspaceSwitched) {
                    onWorkspaceSwitched()
                  } else {
                    window.location.reload()
                  }
                }}
                style={{ fontWeight: 600, padding: '6px 16px' }}
              >
                {isDeletingWs ? 'Deleting...' : 'Delete Workspace'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
