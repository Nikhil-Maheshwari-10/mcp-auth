import React, { useState, useEffect, useMemo } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  UserProfile,
  getMe,
  logout,
  getGitHubConnectUrl,
  disconnectGitHub,
  getGoogleReauthUrl,
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
    icon: '📧',
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
  const [searchQuery, setSearchQuery] = useState('')
  const [disconnectingGitHub, setDisconnectingGitHub] = useState(false)
  const [showSignoutModal, setShowSignoutModal] = useState(false)
  const [signingOut, setSigningOut] = useState(false)

  const handleDisconnectGitHub = async () => {
    setDisconnectingGitHub(true)
    const success = await disconnectGitHub()
    if (success) {
      const updated = await getMe()
      if (updated) setProfile(updated)
    }
    setDisconnectingGitHub(false)
  }

  const githubConnected = !!profile?.connected_providers?.github?.connected
  const githubUsername = profile?.connected_providers?.github?.username
  const googleConnected = !!profile?.email
  const googleName = profile?.connected_providers?.google?.username
  const justConnected = params.get('github') === 'connected'
  const justReauthed = params.get('reauth') === 'success'

  // Scope gap detection — derived from /me response
  const googleMissingScopes: string[] = profile?.connected_providers?.google?.missing_scopes ?? []
  const calendarMissing = googleMissingScopes.includes('calendar')
  const gmailMissing = googleMissingScopes.includes('gmail')
  const hasAnyScopeMissing = googleMissingScopes.length > 0

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

        <div style={{ padding: '12px 8px' }}>
          <div
            className="session-item active"
            style={{ cursor: 'default' }}
          >
            <div className="session-item-title">⚙️ Settings</div>
            <div className="session-item-meta">Tools & Integrations</div>
          </div>
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <div className="sidebar-avatar">
              {profile?.email?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-email">{profile?.email ?? 'Unknown'}</div>
              <div className="sidebar-user-role">Workspace owner</div>
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
          <h1 className="settings-heading">Settings & Agent Tools</h1>
          <p className="settings-sub">Manage your connected accounts and browse all {ALL_TOOLS.length} active agent tools.</p>

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

          {/* Identity Section */}
          <div className="settings-section">
            <div className="settings-section-title">Your Identity</div>
            <div className="settings-card">
              <div className="account-row">
                <div className="account-icon google">🔵</div>
                <div className="account-info">
                  <div className="account-name">{googleName || 'Google Account'}</div>
                  <div className="account-detail">{profile?.email}</div>
                  <div className="account-linked-to">Primary identity · Authenticated via Google OAuth</div>
                </div>
                <div className="account-status">
                  <span className="badge badge-connected">✓ Primary</span>
                </div>
              </div>
            </div>
          </div>

          {/* Connected Accounts Section */}
          <div className="settings-section">
            <div className="settings-section-title">Connected Integrations</div>
            <div className="settings-card">

              {/* Google row */}
              <div className="account-row">
                <div className="account-icon google">
                  <svg width="22" height="22" viewBox="0 0 18 18">
                    <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/>
                    <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.72.48-1.63.77-2.7.77-2.07 0-3.82-1.4-4.45-3.28H1.87v2.07A8 8 0 0 0 8.98 17z"/>
                    <path fill="#FBBC05" d="M4.53 10.54A4.87 4.87 0 0 1 4.27 9c0-.53.09-1.05.26-1.54V5.39H1.87A8 8 0 0 0 .98 9c0 1.29.31 2.51.89 3.61l2.66-2.07z"/>
                    <path fill="#EA4335" d="M8.98 3.58c1.16 0 2.21.4 3.03 1.18l2.27-2.27A8 8 0 0 0 .98 9l2.85 2.07C4.3 5.07 6.35 3.58 8.98 3.58z"/>
                  </svg>
                </div>
                <div className="account-info">
                  <div className="account-name">Google Workspace</div>
                  <div className="account-detail">
                    {profile?.email} · {hasAnyScopeMissing
                      ? `${14 - (calendarMissing ? 6 : 0) - (gmailMissing ? 8 : 0)} of 14 tools active`
                      : '14 Gmail & Calendar tools active'}
                  </div>
                  {hasAnyScopeMissing && (
                    <div style={{ fontSize: 12, color: 'var(--warning)', marginTop: 4 }}>
                      ⚠️ Missing: {googleMissingScopes.join(', ')} permissions
                    </div>
                  )}
                </div>
                <div className="account-status" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
                  <span className="badge badge-connected">✓ Connected</span>
                  {hasAnyScopeMissing && (
                    <a
                      href={getGoogleReauthUrl()}
                      className="btn btn-ghost btn-sm"
                      id="reauthorize-google-btn"
                      style={{ fontSize: 12, whiteSpace: 'nowrap' }}
                    >
                      🔑 Re-authorize
                    </a>
                  )}
                </div>
              </div>

              {/* GitHub row */}
              <div className="account-row">
                <div className="account-icon github">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="var(--text-primary)">
                    <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"/>
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
                        <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2z"/>
                      </svg>
                      Connect GitHub
                    </a>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Tools Showcase Section */}
          <div className="settings-section">
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
                📧 Gmail (8)
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
                            href={getGoogleReauthUrl()}
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

          {/* Danger zone / Sign out */}
          <div className="settings-section">
            <div className="settings-section-title">Account</div>
            <div className="settings-card">
              <div className="account-row">
                <div className="account-info">
                  <div className="account-name">Sign out</div>
                  <div className="account-detail">Clear your active session and return to login</div>
                </div>
                <button
                  className="btn btn-ghost btn-sm"
                  id="signout-btn"
                  onClick={() => setShowSignoutModal(true)}
                >
                  Sign out
                </button>
              </div>
            </div>
          </div>
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
            padding: '24px',
            maxWidth: 420,
            width: '100%',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
              <span style={{ fontSize: 32, flexShrink: 0, lineHeight: 1 }}>⚠️</span>
              <div>
                <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>
                  Sign out of Workspace?
                </h3>
                <p style={{ margin: '2px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
                  Are you sure you want to log out?
                </p>
              </div>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 20 }}>
              This will clear your active session for <strong>{profile?.email}</strong> and return you to the login screen.
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setShowSignoutModal(false)}
                disabled={signingOut}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-sm"
                id="confirm-signout-btn"
                style={{
                  background: '#ef4444',
                  color: '#ffffff',
                  border: 'none',
                  fontWeight: 600,
                  cursor: signingOut ? 'not-allowed' : 'pointer'
                }}
                disabled={signingOut}
                onClick={async () => {
                  setSigningOut(true)
                  await logout()
                  navigate('/login')
                }}
              >
                {signingOut ? 'Signing out...' : 'Yes, Sign Out'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

