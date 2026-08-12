import React, { useState, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  UserProfile,
  getMe,
  logout,
  getGitHubConnectUrl,
  disconnectGitHub,
  getGoogleReauthUrl,
  getGoogleAddAccountUrl,
  removeGoogleAccount,
  setGoogleActiveAccount,
  deleteWorkspace,
  createWorkspace,
  switchWorkspace,
} from '../lib/api'

interface ToolItem {
  id: string
  icon: string
  name: string
  description: string
  provider: 'google' | 'github'
  category: 'gmail' | 'calendar' | 'github'
  scopeType?: 'read' | 'write'
}

const ALL_TOOLS: ToolItem[] = [
  // ─── Gmail Tools (8) ───
  {
    id: 'gmail_get_email',
    icon: '📖',
    name: 'Read Email Body & Details',
    description: 'Fetches full body text, headers, and sender information with clean text extraction.',
    provider: 'google',
    category: 'gmail',
    scopeType: 'read',
  },
  {
    id: 'gmail_search_emails',
    icon: '🔍',
    name: 'Search Emails',
    description: 'Searches messages across Gmail using operators (is:unread, from:, has:attachment).',
    provider: 'google',
    category: 'gmail',
    scopeType: 'read',
  },
  {
    id: 'gmail_mark_as_read',
    icon: '👁️',
    name: 'Mark as Read',
    description: 'Removes the UNREAD label from any specified email message.',
    provider: 'google',
    category: 'gmail',
    scopeType: 'write',
  },
  {
    id: 'google_list_emails',
    icon: '📩',
    name: 'List Recent Emails',
    description: 'Lists recent inbox messages with subject lines, snippets, and timestamps.',
    provider: 'google',
    category: 'gmail',
    scopeType: 'read',
  },
  {
    id: 'gmail_send',
    icon: '📤',
    name: 'Send Email',
    description: 'Drafts and sends emails to recipients with CC and BCC options.',
    provider: 'google',
    category: 'gmail',
    scopeType: 'write',
  },
  {
    id: 'gmail_reply',
    icon: '↩️',
    name: 'Reply to Thread',
    description: 'Sends a contextual reply to an existing email conversation thread.',
    provider: 'google',
    category: 'gmail',
    scopeType: 'write',
  },
  {
    id: 'gmail_archive',
    icon: '📁',
    name: 'Archive Email',
    description: 'Archives emails out of the primary inbox folder.',
    provider: 'google',
    category: 'gmail',
    scopeType: 'write',
  },
  {
    id: 'google_whoami',
    icon: '👤',
    name: 'Google Profile Info',
    description: 'Verifies the connected Google account identity and email address.',
    provider: 'google',
    category: 'gmail',
    scopeType: 'read',
  },

  // ─── Calendar Tools (6) ───
  {
    id: 'calendar_search_events',
    icon: '🔎',
    name: 'Search Calendar Events',
    description: 'Searches meetings and events by keyword and custom date/time ranges.',
    provider: 'google',
    category: 'calendar',
    scopeType: 'read',
  },
  {
    id: 'calendar_get_event',
    icon: '📋',
    name: 'Get Event Details',
    description: 'Retrieves complete event details, attendees status, notes, and video conference links.',
    provider: 'google',
    category: 'calendar',
    scopeType: 'read',
  },
  {
    id: 'google_list_calendar_events',
    icon: '📅',
    name: 'List Upcoming Events',
    description: 'Lists upcoming calendar events and meetings from primary calendar.',
    provider: 'google',
    category: 'calendar',
    scopeType: 'read',
  },
  {
    id: 'calendar_create_event',
    icon: '➕',
    name: 'Schedule New Event',
    description: 'Creates and schedules new calendar meetings with attendees and location.',
    provider: 'google',
    category: 'calendar',
    scopeType: 'write',
  },
  {
    id: 'calendar_update_event',
    icon: '✏️',
    name: 'Update Event',
    description: 'Modifies event summary, start/end time, description, or attendees.',
    provider: 'google',
    category: 'calendar',
    scopeType: 'write',
  },
  {
    id: 'calendar_delete_event',
    icon: '🗑️',
    name: 'Cancel / Delete Event',
    description: 'Deletes or cancels scheduled calendar events.',
    provider: 'google',
    category: 'calendar',
    scopeType: 'write',
  },

  // ─── GitHub Tools (11) ───
  {
    id: 'github_get_issue',
    icon: '🐞',
    name: 'Get Issue Details & Comments',
    description: 'Reads the full issue body, labels, assignees, and discussion thread.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_get_pr',
    icon: '🔍',
    name: 'Get Pull Request Details',
    description: 'Reads PR description, branch refs, merge status, and changed files.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_get_file_contents',
    icon: '📄',
    name: 'Read Repo File Contents',
    description: 'Fetches and decodes text files (code, README, configs) directly from any repo branch.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_list_repos',
    icon: '📦',
    name: 'List Repositories',
    description: 'Lists owned and accessible repositories with stars, visibility, and forks.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_list_issues',
    icon: '🐛',
    name: 'List Issues',
    description: 'Filters and lists repository issues by state, label, and assignee.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_create_issue',
    icon: '💡',
    name: 'Create Issue',
    description: 'Opens new issues with title, description markdown, and labels.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_comment_on_issue',
    icon: '💬',
    name: 'Comment on Issue / PR',
    description: 'Adds discussion comments to issues and pull requests.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_close_issue',
    icon: '✅',
    name: 'Close Issue',
    description: 'Closes completed or resolved issues on repositories.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_list_pull_requests',
    icon: '🔀',
    name: 'List Pull Requests',
    description: 'Lists open and merged pull requests with branch details.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_create_pr',
    icon: '🚀',
    name: 'Create Pull Request',
    description: 'Opens new pull requests comparing head and base branches.',
    provider: 'github',
    category: 'github',
  },
  {
    id: 'github_whoami',
    icon: '👾',
    name: 'GitHub Profile Info',
    description: 'Retrieves connected GitHub user profile and permissions.',
    provider: 'github',
    category: 'github',
  },
]

export default function SettingsPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()

  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'all' | 'gmail' | 'calendar' | 'github'>('all')
  const [activeSection, setActiveSection] = useState<'profile' | 'integrations' | 'tools'>('profile')
  const [searchQuery, setSearchQuery] = useState('')
  const [disconnectingGitHub, setDisconnectingGitHub] = useState(false)
  const [showSignoutModal, setShowSignoutModal] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  const switchSection = (sectionName: 'profile' | 'integrations' | 'tools') => {
    setActiveSection(sectionName)
  }

  const [removingAccountId, setRemovingAccountId] = useState<string | null>(null)
  const [settingActiveId, setSettingActiveId] = useState<string | null>(null)
  const [deletingWs, setDeletingWs] = useState<{ id: string; name: string } | null>(null)
  const [isDeletingWs, setIsDeletingWs] = useState(false)

  // Create Workspace Modal State
  const [showCreateWsModal, setShowCreateWsModal] = useState(false)
  const [createWsIntent, setCreateWsIntent] = useState<'switch' | 'add-account'>('switch')
  const [newWsName, setNewWsName] = useState('')
  const [creatingWs, setCreatingWs] = useState(false)

  const handleOpenCreateWsModal = (intent: 'switch' | 'add-account' = 'switch') => {
    setCreateWsIntent(intent)
    setNewWsName('')
    setShowCreateWsModal(true)
  }

  const handleCreateWorkspaceSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newWsName.trim() || creatingWs) return
    setCreatingWs(true)

    try {
      const res = await createWorkspace(newWsName.trim())
      if (res) {
        if (createWsIntent === 'add-account') {
          window.location.href = getGoogleAddAccountUrl()
        } else {
          window.location.reload()
        }
      }
    } catch (err) {
      console.error('Failed to create workspace', err)
    } finally {
      setCreatingWs(false)
    }
  }

  const handleSetActive = async (accountId: string) => {
    setSettingActiveId(accountId)
    const success = await setGoogleActiveAccount(accountId)
    if (success) {
      const updated = await getMe()
      if (updated) setProfile(updated)
    }
    setSettingActiveId(null)
  }

  const handleDisconnectGitHub = async () => {
    setDisconnectingGitHub(true)
    const success = await disconnectGitHub()
    if (success) {
      const updated = await getMe()
      if (updated) setProfile(updated)
    }
    setDisconnectingGitHub(false)
  }

  const handleRemoveAccount = async (accountId: string) => {
    setRemovingAccountId(accountId)
    const success = await removeGoogleAccount(accountId)
    if (success) {
      const updated = await getMe()
      if (updated) setProfile(updated)
    }
    setRemovingAccountId(null)
  }

  const githubConnected = !!profile?.connected_providers?.github?.connected
  const githubUsername = profile?.connected_providers?.github?.username
  const googleConnected = !!profile?.email
  const googleName = profile?.connected_providers?.google?.username
  const googleAccounts: Array<{ email: string; provider_account_id: string; is_active: boolean; missing_scopes: string[]; avatar_url?: string | null }> =
    profile?.connected_providers?.google?.accounts ?? []
  const primaryAccount = googleAccounts.find(a => a.email === profile?.email) ?? googleAccounts.find(a => a.is_active) ?? googleAccounts[0]
  const primaryAvatarUrl = primaryAccount?.avatar_url ?? googleAccounts.find(a => !!a.avatar_url)?.avatar_url ?? null
  const justConnected = params.get('github') === 'connected'
  const justReauthed = params.get('reauth') === 'success'

  // Scope gap detection — derived from /me response
  const googleMissingScopes: string[] = profile?.connected_providers?.google?.missing_scopes ?? []
  const calendarMissing = googleMissingScopes.includes('calendar')
  const gmailMissing = googleMissingScopes.includes('gmail')
  const hasAnyScopeMissing = googleMissingScopes.length > 0

  const sortedGoogleAccounts = useMemo(() => {
    const list = googleAccounts.length > 0
      ? [...googleAccounts]
      : [{ email: profile?.email ?? 'Connected Account', provider_account_id: 'primary', is_active: true, missing_scopes: googleMissingScopes, avatar_url: primaryAvatarUrl }]

    const ownerEmail = profile?.email
    return list.sort((a, b) => {
      if (a.email === ownerEmail) return -1
      if (b.email === ownerEmail) return 1
      return 0
    })
  }, [googleAccounts, profile?.email, googleMissingScopes, primaryAvatarUrl])

  // Also read missing_scopes from URL (set on initial login if partial consent)
  const urlMissingScopes = params.get('missing_scopes')?.split(',').filter(Boolean) ?? []

  useEffect(() => {
    getMe().then((p) => {
      if (!p) { navigate('/login'); return }
      setProfile(p)
    }).finally(() => setLoading(false))
  }, [navigate])

  const filteredTools = useMemo(() => {
    return ALL_TOOLS.filter((t) => {
      const matchesTab =
        activeTab === 'all'
          ? true
          : t.category === activeTab

      if (!matchesTab) return false

      if (!searchQuery.trim()) return true

      const q = searchQuery.toLowerCase()
      return (
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.provider.toLowerCase().includes(q)
      )
    })
  }, [activeTab, searchQuery])

  if (loading) {
    return (
      <div className="app-shell">
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div className="spinner" />
        </div>
      </div>
    )
  }

  return (
    <div className="app-shell">
      {/* Minimal sidebar for navigation on desktop */}
      <aside className="sidebar settings-sidebar">
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="sidebar-brand-left">
              <div className="sidebar-brand-icon">🤖</div>
              <span className="sidebar-brand-name">Workspace</span>
            </div>
          </div>
          <button className="btn sidebar-new-btn" onClick={() => navigate('/')} id="back-to-chat-btn">
            ← Back to Chat
          </button>
        </div>

        <div style={{ padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 6 }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--text-muted)', padding: '0 8px 4px', textTransform: 'uppercase', letterSpacing: '0.6px' }}>
            Settings Sections
          </div>

          <div
            className={`session-item ${activeSection === 'profile' ? 'active' : ''}`}
            onClick={() => switchSection('profile')}
            style={{ cursor: 'pointer' }}
          >
            <div className="session-item-content">
              <div className="session-item-title">👤 Profile &amp; Identity</div>
              <div className="session-item-meta">Primary identity details</div>
            </div>
          </div>

          <div
            className={`session-item ${activeSection === 'integrations' ? 'active' : ''}`}
            onClick={() => switchSection('integrations')}
            style={{ cursor: 'pointer' }}
          >
            <div className="session-item-content">
              <div className="session-item-title">⚡ Connected Integrations</div>
              <div className="session-item-meta">Google Workspace &amp; GitHub</div>
            </div>
          </div>

          <div
            className={`session-item ${activeSection === 'tools' ? 'active' : ''}`}
            onClick={() => switchSection('tools')}
            style={{ cursor: 'pointer' }}
          >
            <div className="session-item-content">
              <div className="session-item-title">🛠️ Agent Tools</div>
              <div className="session-item-meta">{ALL_TOOLS.length} Active MCP Tools</div>
            </div>
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-user" style={{ cursor: 'default' }}>
            <div style={{ display: 'flex', alignItems: 'center' }}>
              {sortedGoogleAccounts.length > 1 ? (
                <div style={{ display: 'flex', alignItems: 'center' }}>
                  {sortedGoogleAccounts.slice(0, 3).map((acc, idx) => (
                    <div
                      key={acc.provider_account_id}
                      className="sidebar-avatar"
                      style={{
                        width: 28,
                        height: 28,
                        marginLeft: idx === 0 ? 0 : -8,
                        zIndex: 3 - idx,
                        border: '2px solid var(--bg-surface)',
                        overflow: 'hidden',
                        padding: 0,
                        flexShrink: 0,
                      }}
                    >
                      {acc.avatar_url ? (
                        <img src={acc.avatar_url} alt={acc.email} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                      ) : (
                        <div style={{ width: '100%', height: '100%', background: 'linear-gradient(135deg, #6366f1, #a855f7)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 11, fontWeight: 700 }}>
                          {acc.email[0]?.toUpperCase() ?? 'G'}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="sidebar-avatar" style={{ padding: 0, overflow: 'hidden', background: primaryAvatarUrl ? 'none' : undefined }}>
                  {primaryAvatarUrl ? (
                    <img
                      src={primaryAvatarUrl}
                      alt={profile?.email ?? 'User'}
                      style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' }}
                    />
                  ) : (
                    profile?.email?.[0]?.toUpperCase() ?? '?'
                  )}
                </div>
              )}
            </div>
            <div className="sidebar-user-info" style={{ marginLeft: sortedGoogleAccounts.length > 1 ? 6 : 0 }}>
              <div className="sidebar-user-email">{profile?.email ?? 'Unknown'}</div>
              <div className="sidebar-user-role" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                {googleAccounts.length > 1 ? `● ${googleAccounts.length} Connected Accounts` : 'Workspace owner'}
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Settings Content */}
      <main className="chat-area" style={{ overflowY: 'auto', background: 'var(--bg-base)' }}>
        {/* Mobile top bar for back navigation */}
        <div className="settings-mobile-topbar">
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/')} id="mobile-back-to-chat-btn">
            ← Back to Chat
          </button>
          <div className="settings-mobile-title">⚙️ Settings</div>
        </div>

        <div className="settings-page">
          {activeSection === 'profile' && (
            <>
              <h1 className="settings-heading">Profile &amp; Identity</h1>
              <p className="settings-sub">Manage your primary Google identity, connected accounts, and workspace options.</p>
            </>
          )}
          {activeSection === 'integrations' && (
            <>
              <h1 className="settings-heading">Connected Integrations</h1>
              <p className="settings-sub">Manage your linked Google Workspace accounts and GitHub OAuth integrations.</p>
            </>
          )}
          {activeSection === 'tools' && (
            <>
              <h1 className="settings-heading">Agent Tools &amp; Capabilities</h1>
              <p className="settings-sub">Browse and search all {ALL_TOOLS.length} active MCP agent tools across Gmail, Calendar, and GitHub.</p>
            </>
          )}

          {/* Reauth success toast */}
          {justReauthed && !hasAnyScopeMissing && (
            <div style={{
              padding: '12px 16px',
              background: 'rgba(34,197,94,0.08)',
              border: '1px solid rgba(34,197,94,0.2)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--success)',
              fontSize: 13,
              marginBottom: 24,
              display: 'flex', alignItems: 'center', gap: 10,
              animation: 'fadeInDown 0.3s ease',
            }}>
              ✅ <span>Google re-authorization successful! All scopes are now active.</span>
            </div>
          )}

          {/* Reauth success but still missing some scopes */}
          {justReauthed && hasAnyScopeMissing && (
            <div style={{
              padding: '12px 16px',
              background: 'rgba(245,158,11,0.08)',
              border: '1px solid rgba(245,158,11,0.2)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--warning)',
              fontSize: 13,
              marginBottom: 24,
              display: 'flex', alignItems: 'center', gap: 10,
              animation: 'fadeInDown 0.3s ease',
            }}>
              ⚠️ <span>Some permissions were still not granted: <strong>{googleMissingScopes.join(', ')}</strong>. Click Re-authorize below to try again.</span>
            </div>
          )}

          {/* Scope gap banner from initial login redirect */}
          {!justReauthed && urlMissingScopes.length > 0 && (
            <div style={{
              padding: '12px 16px',
              background: 'rgba(245,158,11,0.08)',
              border: '1px solid rgba(245,158,11,0.2)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--warning)',
              fontSize: 13,
              marginBottom: 24,
              display: 'flex', alignItems: 'center', gap: 10,
              animation: 'fadeInDown 0.3s ease',
            }}>
              ⚠️ <span>You didn't grant access to: <strong>{urlMissingScopes.join(', ')}</strong>. Some tools will be unavailable until you re-authorize.</span>
            </div>
          )}

          {/* GitHub just connected toast */}
          {justConnected && (
            <div style={{
              padding: '12px 16px',
              background: 'rgba(34,197,94,0.08)',
              border: '1px solid rgba(34,197,94,0.2)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--success)',
              fontSize: 13,
              marginBottom: 24,
              display: 'flex', alignItems: 'center', gap: 10,
              animation: 'fadeInDown 0.3s ease',
            }}>
              ✅ <span>GitHub connected successfully! All {ALL_TOOLS.filter(t => t.provider === 'github').length} GitHub tools are now active.</span>
            </div>
          )}

          {/* Profile & Identity Section View */}
          {activeSection === 'profile' && (
            <div className="settings-section" id="identity-section">
              {/* Workspace Management Card — only when active workspace is selected */}
              {profile?.workspace_id && (
                <div className="settings-card" style={{ marginBottom: 24, padding: '20px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--text-muted)' }}>
                      Active Workspace
                    </div>
                  </div>
                  <div style={{ padding: 0, border: 'none', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div className="account-icon google" style={{ padding: 0, overflow: 'hidden', background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)', width: 44, height: 44, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 20, fontWeight: 700 }}>
                        🏢
                      </div>
                      <div className="account-info">
                        <div className="account-name" style={{ fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>
                          {profile?.workspace_name || 'My Workspace'}
                        </div>
                        <div className="account-linked-to" style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                          {profile.workspaces?.length || 1} workspace{(profile.workspaces?.length || 1) !== 1 ? 's' : ''} available
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center' }}>
                        {sortedGoogleAccounts.slice(0, 4).map((acc: any, idx: number) => (
                          <div
                            key={acc.provider_account_id}
                            style={{
                              width: 32,
                              height: 32,
                              borderRadius: '50%',
                              marginLeft: idx === 0 ? 0 : -10,
                              zIndex: 4 - idx,
                              border: '2px solid var(--bg-card)',
                              overflow: 'hidden',
                              background: 'rgba(255, 255, 255, 0.08)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              flexShrink: 0,
                            }}
                            title={acc.email}
                          >
                            {acc.avatar_url ? (
                              <img src={acc.avatar_url} alt={acc.email} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              <div style={{ width: '100%', height: '100%', background: 'linear-gradient(135deg, #6366f1, #a855f7)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 12, fontWeight: 700 }}>
                                {acc.email[0]?.toUpperCase() ?? 'G'}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', fontWeight: 500 }}>
                        {sortedGoogleAccounts.length} account{sortedGoogleAccounts.length !== 1 ? 's' : ''}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* Card 1: Primary Workspace Identity */}
              <div className="settings-card" style={{ marginBottom: 24, padding: '20px' }}>
                <div style={{ fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px', color: 'var(--text-muted)', marginBottom: 14 }}>
                  Workspace Primary Identity
                </div>
                <div className="account-row" style={{ padding: 0, border: 'none' }}>
                  <div className="account-icon google" style={{ padding: 0, overflow: 'hidden', background: 'none', border: 'none', width: 48, height: 48, flexShrink: 0 }}>
                    {primaryAvatarUrl ? (
                      <img
                        src={primaryAvatarUrl}
                        alt={profile?.email || 'User'}
                        style={{ width: 48, height: 48, borderRadius: '50%', objectFit: 'cover', border: '2px solid rgba(255,255,255,0.15)' }}
                      />
                    ) : (
                      <div style={{ width: 48, height: 48, borderRadius: '50%', background: 'linear-gradient(135deg, #6366f1, #a855f7)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontWeight: 700, fontSize: 20 }}>
                        {(primaryAccount?.email ?? profile?.email)?.[0]?.toUpperCase() ?? 'U'}
                      </div>
                    )}
                  </div>
                  <div className="account-info">
                    <div className="account-name" style={{ fontSize: 17, fontWeight: 600, color: 'var(--text-primary)' }}>
                      {primaryAccount?.email ?? profile?.email}
                    </div>
                    <div className="account-linked-to" style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
                      Primary workspace owner · Authenticated via Google OAuth
                    </div>
                  </div>
                  <div className="account-status" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span className="badge badge-connected" style={{ fontSize: 12, padding: '4px 10px' }}>✓ Primary Owner</span>
                  </div>
                </div>
              </div>

              {/* Card 2: Connected Google Workspace & Gmail Accounts */}
              <div className="settings-card" style={{ marginBottom: 24 }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div className="account-icon google">
                      <svg width="22" height="22" viewBox="0 0 18 18">
                        <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z" />
                        <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.72.48-1.63.77-2.7.77-2.07 0-3.82-1.4-4.45-3.28H1.87v2.07A8 8 0 0 0 8.98 17z" />
                        <path fill="#FBBC05" d="M4.53 10.54A4.87 4.87 0 0 1 4.27 9c0-.53.09-1.05.26-1.54V5.39H1.87A8 8 0 0 0 .98 9c0 1.29.31 2.51.89 3.61l2.66-2.07z" />
                        <path fill="#EA4335" d="M8.98 3.58c1.16 0 2.21.4 3.03 1.18l2.27-2.27A8 8 0 0 0 .98 9l2.85 2.07C4.3 5.07 6.35 3.58 8.98 3.58z" />
                      </svg>
                    </div>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)' }}>
                        Google Workspace Accounts ({googleAccounts.length || 1})
                      </div>
                      <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        Connected Gmail &amp; Calendar accounts available to AI agent tools
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
                    onClick={() => {
                      if (!profile?.workspace_id) {
                        handleOpenCreateWsModal('add-account')
                      } else {
                        window.location.href = getGoogleAddAccountUrl()
                      }
                    }}
                  >
                    ➕ Add Account
                  </button>
                </div>

                {/* Accounts List */}
                <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {sortedGoogleAccounts.map((acc) => {
                    const isOwner = acc.email === profile?.email
                    return (
                      <div
                        key={acc.provider_account_id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '12px 16px',
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-md)',
                          transition: 'all 0.2s ease',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <div style={{ width: 34, height: 34, borderRadius: '50%', overflow: 'hidden', flexShrink: 0, border: '1.5px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 600, color: '#fff', fontSize: 14 }}>
                            {acc.avatar_url ? (
                              <img src={acc.avatar_url} alt={acc.email} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              acc.email[0]?.toUpperCase() ?? 'G'
                            )}
                          </div>
                          <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <span style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)' }}>
                                {acc.email}
                              </span>
                            </div>
                            {acc.missing_scopes && acc.missing_scopes.length > 0 && (
                              <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 2 }}>
                                ⚠️ Missing permissions: {acc.missing_scopes.join(', ')}
                              </div>
                            )}
                          </div>
                        </div>

                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          {acc.missing_scopes && acc.missing_scopes.length > 0 && (
                            <a
                              href={getGoogleReauthUrl(acc.email)}
                              className="btn btn-ghost btn-sm"
                              style={{ fontSize: 11, padding: '4px 10px' }}
                            >
                              🔑 Re-auth
                            </a>
                          )}
                          {!isOwner && (
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              disabled={removingAccountId === acc.provider_account_id}
                              onClick={() => handleRemoveAccount(acc.provider_account_id)}
                              style={{ fontSize: 11, color: 'var(--danger)', padding: '4px 10px' }}
                            >
                              {removingAccountId === acc.provider_account_id ? 'Removing...' : 'Remove'}
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* Card 3: Workspace Session & Sign Out */}
              <div className="settings-card" style={{ padding: '18px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
                    Sign out
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
                    Sign out of your active browser session on this device
                  </div>
                </div>
                <button
                  type="button"
                  className="btn-signout-danger"
                  id="settings-session-signout-btn"
                  onClick={() => setShowSignoutModal(true)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                    <polyline points="16 17 21 12 16 7"></polyline>
                    <line x1="21" y1="12" x2="9" y2="12"></line>
                  </svg>
                  <span>Sign Out</span>
                </button>
              </div>
            </div>
          )}

          {/* Connected Accounts & Integrations Section View */}
          {activeSection === 'integrations' && (
            <div className="settings-section" id="integrations-section">
              <div className="settings-card">

                {/* Google Workspace & Accounts */}
                <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                      <div className="account-icon google">
                        <svg width="22" height="22" viewBox="0 0 18 18">
                          <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z" />
                          <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.72.48-1.63.77-2.7.77-2.07 0-3.82-1.4-4.45-3.28H1.87v2.07A8 8 0 0 0 8.98 17z" />
                          <path fill="#FBBC05" d="M4.53 10.54A4.87 4.87 0 0 1 4.27 9c0-.53.09-1.05.26-1.54V5.39H1.87A8 8 0 0 0 .98 9c0 1.29.31 2.51.89 3.61l2.66-2.07z" />
                          <path fill="#EA4335" d="M8.98 3.58c1.16 0 2.21.4 3.03 1.18l2.27-2.27A8 8 0 0 0 .98 9l2.85 2.07C4.3 5.07 6.35 3.58 8.98 3.58z" />
                        </svg>
                      </div>
                      <div>
                        <div className="account-name" style={{ fontSize: 15, fontWeight: 600 }}>Google Workspace & Gmail</div>
                        <div className="account-detail" style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                          {(profile?.connected_providers?.google?.accounts?.length ?? 1)} connected account(s) · 14 Gmail & Calendar tools active
                        </div>
                      </div>
                    </div>
                    <a
                      href={getGoogleAddAccountUrl()}
                      className="btn btn-ghost btn-sm"
                      id="add-google-account-btn"
                      style={{ fontSize: 12, display: 'flex', alignItems: 'center', gap: 6 }}
                    >
                      ➕ Add Gmail Account
                    </a>
                  </div>

                  {/* List of connected accounts */}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
                    {sortedGoogleAccounts.map((acc) => {
                      const isOwner = acc.email === profile?.email
                      return (
                        <div
                          key={acc.provider_account_id}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '10px 14px',
                            background: 'var(--bg-card)',
                            border: '1px solid var(--border)',
                            borderRadius: 'var(--radius-md)',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            {/* Per-account profile picture */}
                            <div style={{ width: 28, height: 28, borderRadius: '50%', overflow: 'hidden', flexShrink: 0, border: '1.5px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                              {(acc as any).avatar_url ? (
                                <img src={(acc as any).avatar_url} alt={acc.email} style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '50%' }} />
                              ) : (
                                <svg width="14" height="14" viewBox="0 0 18 18">
                                  <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z" />
                                  <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.72.48-1.63.77-2.7.77-2.07 0-3.82-1.4-4.45-3.28H1.87v2.07A8 8 0 0 0 8.98 17z" />
                                  <path fill="#FBBC05" d="M4.53 10.54A4.87 4.87 0 0 1 4.27 9c0-.53.09-1.05.26-1.54V5.39H1.87A8 8 0 0 0 .98 9c0 1.29.31 2.51.89 3.61l2.66-2.07z" />
                                  <path fill="#EA4335" d="M8.98 3.58c1.16 0 2.21.4 3.03 1.18l2.27-2.27A8 8 0 0 0 .98 9l2.85 2.07C4.3 5.07 6.35 3.58 8.98 3.58z" />
                                </svg>
                              )}
                            </div>
                            <div>
                              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                                {acc.email}
                              </div>
                              {acc.missing_scopes && acc.missing_scopes.length > 0 && (
                                <div style={{ fontSize: 11, color: 'var(--warning)', marginTop: 2 }}>
                                  ⚠️ Missing: {acc.missing_scopes.join(', ')}
                                </div>
                              )}
                            </div>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            {acc.missing_scopes && acc.missing_scopes.length > 0 && (
                              <a
                                href={getGoogleReauthUrl(acc.email)}
                                className="btn btn-ghost btn-sm"
                                style={{ fontSize: 11, padding: '2px 8px' }}
                              >
                                🔑 Re-auth
                              </a>
                            )}
                            {!isOwner && (
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                disabled={removingAccountId === acc.provider_account_id}
                                onClick={() => handleRemoveAccount(acc.provider_account_id)}
                                style={{ fontSize: 11, color: 'var(--danger)', padding: '2px 8px' }}
                              >
                              </button>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* GitHub row */}
                <div className="account-row">
                  <div className="account-icon github">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="var(--text-primary)">
                      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
                    </svg>
                  </div>
                  <div className="account-info">
                    <div className="account-name">GitHub</div>
                    {githubConnected ? (
                      <>
                        <div className="account-detail">@{githubUsername} · 11 Repos, Issues, PRs & File tools active</div>
                        <div className="account-linked-to">Linked to {profile?.email}</div>
                      </>
                    ) : (
                      <div className="account-detail" style={{ color: 'var(--text-muted)' }}>
                        Not connected · Connect to unlock 11 GitHub developer tools
                      </div>
                    )}
                  </div>
                  <div className="account-status">
                    {githubConnected ? (
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                        <span className="badge badge-connected">✓ Connected</span>
                        <button
                          className="btn btn-ghost btn-sm"
                          id="disconnect-github-btn"
                          onClick={handleDisconnectGitHub}
                          disabled={disconnectingGitHub}
                          style={{ fontSize: 12, color: 'var(--text-muted)' }}
                        >
                          {disconnectingGitHub ? 'Disconnecting...' : 'Disconnect'}
                        </button>
                      </div>
                    ) : (
                      <a
                        href={getGitHubConnectUrl()}
                        className="btn btn-ghost btn-sm"
                        id="connect-github-settings-btn"
                      >
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                          <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z" />
                        </svg>
                        Connect GitHub
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tools Showcase Section View */}
          {activeSection === 'tools' && (
            <div className="settings-section" id="tools-section">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                <div className="settings-section-title" style={{ margin: 0 }}>
                  Agent Tools ({filteredTools.length} of {ALL_TOOLS.length})
                </div>
              </div>

              {/* Filter Pills */}
              <div className="filter-pills">
                <button
                  className={`filter-pill ${activeTab === 'all' ? 'active' : ''}`}
                  onClick={() => setActiveTab('all')}
                >
                  All Tools ({ALL_TOOLS.length})
                </button>
                <button
                  className={`filter-pill ${activeTab === 'gmail' ? 'active' : ''}`}
                  onClick={() => setActiveTab('gmail')}
                >
                  📩 Gmail (8)
                </button>
                <button
                  className={`filter-pill ${activeTab === 'calendar' ? 'active' : ''}`}
                  onClick={() => setActiveTab('calendar')}
                >
                  📅 Calendar (6)
                </button>
                <button
                  className={`filter-pill ${activeTab === 'github' ? 'active' : ''}`}
                  onClick={() => setActiveTab('github')}
                >
                  🐙 GitHub (11)
                </button>
              </div>

              {/* Search Input */}
              <input
                type="text"
                className="tool-search-input"
                placeholder="Search tools by name or description..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />

              {/* Tools List */}
              <div className="settings-card">
                {filteredTools.length === 0 ? (
                  <div style={{ padding: '32px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 14 }}>
                    No tools found matching "{searchQuery}".
                  </div>
                ) : (
                  filteredTools.map((tool) => {
                    const isWriteTool = tool.scopeType === 'write'
                    const isScopeBlocked = isWriteTool && (
                      (tool.category === 'calendar' && calendarMissing) ||
                      (tool.category === 'gmail' && gmailMissing)
                    )
                    const isAvailable = tool.provider === 'google'
                      ? (googleConnected && !isScopeBlocked)
                      : githubConnected

                    return (
                      <div key={tool.id} className="account-row">
                        <div style={{ fontSize: 22, width: 40, textAlign: 'center' }}>{tool.icon}</div>
                        <div className="account-info">
                          <div className="account-name" style={{ fontSize: 14, marginBottom: 2 }}>
                            {tool.name}
                            {isWriteTool && (
                              <span style={{ fontSize: 10, padding: '2px 6px', background: 'rgba(99,102,241,0.12)', color: 'var(--accent-light)', borderRadius: 4, marginLeft: 8, fontWeight: 600 }}>
                                WRITE
                              </span>
                            )}
                          </div>
                          <div className="account-detail">{tool.description}</div>
                        </div>
                        <div className="account-status">
                          {isAvailable ? (
                            <span className="badge badge-connected">✓ Active</span>
                          ) : isScopeBlocked ? (
                            <a
                              href={getGoogleReauthUrl(primaryAccount?.email)}
                              className="badge"
                              style={{ background: 'rgba(245,158,11,0.1)', color: 'var(--warning)', border: '1px solid rgba(245,158,11,0.25)', textDecoration: 'none', cursor: 'pointer', whiteSpace: 'nowrap' }}
                              title={`Grant ${tool.category} permission to enable this tool`}
                            >
                              🔑 Re-authorize
                            </a>
                          ) : (
                            <span className="badge badge-disconnected">Unavailable</span>
                          )}
                        </div>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          )}
        </div>
      </main>

      {/* Sign Out Confirmation Modal */}
      {showSignoutModal && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0, 0, 0, 0.7)',
          backdropFilter: 'blur(6px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 9999,
          padding: 16,
          animation: 'fadeIn 0.2s ease',
        }}>
          <div style={{
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius-lg)',
            padding: 'clamp(18px, 5vw, 24px)',
            maxWidth: 440,
            width: '92vw',
            boxSizing: 'border-box',
            boxShadow: '0 24px 48px -12px rgba(0, 0, 0, 0.75)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <span style={{ fontSize: 'clamp(24px, 6vw, 32px)', flexShrink: 0, lineHeight: 1 }}>⚠️</span>
              <div>
                <h3 style={{ margin: 0, fontSize: 'clamp(15px, 4vw, 17px)', fontWeight: 600, color: 'var(--text-primary)' }}>
                  Sign out of Workspace?
                </h3>
                <p style={{ margin: '2px 0 0', fontSize: 'clamp(12px, 3vw, 13px)', color: 'var(--text-muted)' }}>
                  Are you sure you want to log out?
                </p>
              </div>
            </div>
            <p style={{ fontSize: 'clamp(12px, 3vw, 13px)', color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 18, wordBreak: 'break-word' }}>
              Choose how you want to sign out for <strong>{profile?.email}</strong>:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginBottom: 20, width: '100%' }}>
              <button
                type="button"
                className="btn-signout-primary"
                id="confirm-signout-session-btn"
                disabled={signingOut}
                onClick={async () => {
                  setSigningOut(true)
                  await logout(false)
                  navigate('/login')
                }}
              >
                {signingOut ? 'Signing out...' : 'Sign Out of Workspace'}
              </button>

              <div style={{ fontSize: 'clamp(10.5px, 2.8vw, 11.5px)', color: 'var(--text-muted)', textAlign: 'center', marginTop: -4, lineHeight: 1.4, padding: '0 4px' }}>
                ✓ Preserves all connected Google &amp; GitHub accounts for your next login
              </div>

              <button
                type="button"
                className="btn-signout-disconnect"
                id="confirm-signout-all-btn"
                disabled={signingOut}
                onClick={async () => {
                  setSigningOut(true)
                  await logout(true)
                  navigate('/login')
                }}
              >
                {signingOut ? 'Resetting...' : 'Reset This Workspace'}
              </button>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', width: '100%' }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowSignoutModal(false)}
                disabled={signingOut}
                style={{ minHeight: 36, padding: '6px 16px' }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      {/* ─── Delete Workspace Confirmation Modal ────────────────────────────────────── */}
      {deletingWs && (
        <div className="profile-modal-overlay" onClick={() => setDeletingWs(null)}>
          <div
            className="profile-modal-card"
            style={{ maxWidth: 440, width: '92vw', padding: '24px', boxSizing: 'border-box' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
              <div style={{
                width: 42,
                height: 42,
                borderRadius: '12px',
                background: 'rgba(239, 68, 68, 0.15)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--danger)',
                flexShrink: 0,
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  <line x1="10" y1="11" x2="10" y2="17" />
                  <line x1="14" y1="11" x2="14" y2="17" />
                </svg>
              </div>
              <div>
                <h3 style={{ margin: 0, fontSize: 17, fontWeight: 600, color: 'var(--text-primary)' }}>
                  Delete Workspace?
                </h3>
                <p style={{ margin: '3px 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
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
                className="btn btn-ghost"
                onClick={() => setDeletingWs(null)}
                disabled={isDeletingWs}
                style={{ minHeight: 38 }}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger"
                disabled={isDeletingWs}
                onClick={async () => {
                  setIsDeletingWs(true)
                  await deleteWorkspace(deletingWs.id)
                  setIsDeletingWs(false)
                  setDeletingWs(null)
                  const updated = await getMe()
                  if (updated) {
                    setProfile(updated)
                  } else {
                    window.location.reload()
                  }
                }}
                style={{ minHeight: 38, padding: '0 18px', fontWeight: 600 }}
              >
                {isDeletingWs ? 'Deleting...' : 'Delete Workspace'}
              </button>
            </div>
          </div>
        </div>
      )}
      {/* ─── Create Workspace Modal ─────────────────────────────────────────────── */}
      {showCreateWsModal && (
        <div className="profile-modal-overlay" onClick={() => setShowCreateWsModal(false)}>
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
                    {createWsIntent === 'add-account' ? 'Create Workspace to Add Account' : 'Create Workspace'}
                  </h3>
                  <p style={{ margin: '3px 0 0 0', fontSize: 12, color: 'var(--text-muted)' }}>
                    Organize isolated email accounts and chat history
                  </p>
                </div>
              </div>
              <button
                type="button"
                className="btn-icon"
                onClick={() => setShowCreateWsModal(false)}
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: 18, padding: 4 }}
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateWorkspaceSubmit} style={{ marginTop: 18 }}>
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
                  onClick={() => setShowCreateWsModal(false)}
                  disabled={creatingWs}
                  style={{ minHeight: 38 }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={creatingWs || !newWsName.trim()}
                  style={{
                    minHeight: 38,
                    background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                    boxShadow: '0 0 16px rgba(99, 102, 241, 0.4)',
                    color: '#ffffff',
                    fontWeight: 600,
                  }}
                >
                  {creatingWs ? 'Creating...' : createWsIntent === 'add-account' ? 'Create & Add Account' : 'Create Workspace'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

