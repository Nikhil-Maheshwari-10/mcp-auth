import React, { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  UserProfile,
  Session,
  getMe,
  listSessions,
  createSession,
  getSession,
  deleteSession,
  runSse,
  getGitHubConnectUrl,
  getGoogleReauthUrl,
} from '../lib/api'

interface Message {
  id: string
  role: 'user' | 'agent'
  text: string
  streaming?: boolean
  steps?: string[]
}

function extractEventText(event: any): string {
  const parts = event?.content?.parts ?? []
  const texts: string[] = []
  for (const p of parts) {
    if (typeof p?.text === 'string' && p.text.trim()) {
      texts.push(p.text.trim())
    }
  }
  return texts.join('\n\n')
}

function parseEventsToMessages(events: any[]): Message[] {
  const msgs: Message[] = []
  for (const e of events) {
    const text = extractEventText(e)
    if (!text) continue
    const isUser = e.author === 'user' || e.content?.role === 'user'
    msgs.push({
      id: e.id || Math.random().toString(),
      role: isUser ? 'user' : 'agent',
      text,
    })
  }
  return msgs
}

function formatSessionTitle(session: Session): string {
  const events = session.events ?? []
  for (const e of events) {
    const isUser = e.author === 'user' || (e.content as any)?.role === 'user'
    if (isUser) {
      const text = extractEventText(e)
      if (text) {
        return text.length > 36 ? text.slice(0, 36) + '…' : text
      }
    }
  }
  return 'New chat'
}

function formatTime(id: string): string {
  return 'Recent'
}

function getAuthCardInfo(text: string): { type: 'google' | 'github'; label: string; mode?: 'write' } | null {
  const lower = text.toLowerCase()

  // GitHub matching (e.g. "I don't currently have access to your GitHub account")
  if (
    lower.includes('github account') ||
    lower.includes('access to your github') ||
    lower.includes('connect github') ||
    lower.includes('connect your github') ||
    lower.includes('github token') ||
    lower.includes('github integration') ||
    lower.includes('github permissions') ||
    lower.includes('re-authorize github') ||
    lower.includes('missing github') ||
    lower.includes('not connected to github') ||
    lower.includes('github_token')
  ) {
    return { type: 'github', label: 'Connect GitHub Account' }
  }

  // Google matching
  if (
    lower.includes('re-authorize google') ||
    lower.includes('google write permissions') ||
    lower.includes('missing google') ||
    lower.includes('access to your google') ||
    lower.includes('connect google') ||
    lower.includes('gmail write') ||
    lower.includes('calendar write') ||
    lower.includes('gmail_send') ||
    lower.includes('calendar_create') ||
    lower.includes('google.com/auth')
  ) {
    return { type: 'google', label: 'Re-authorize Google Permissions', mode: 'write' }
  }

  return null
}

function cleanMarkdownText(text: string): string {
  if (!text) return ''
  return text
    .replace(/\|\|/g, '|\n|')
    .replace(/^[\s]*---+[\s]*$/gm, '')
    .replace(/^[\s]*\*\*\*+[\s]*$/gm, '')
    .replace(/^[\s]*___+[\s]*$/gm, '')
    .replace(/\$\\rightarrow\$/g, '→')
    .replace(/\\rightarrow/g, '→')
    .replace(/\$\\leftarrow\$/g, '←')
    .replace(/\\leftarrow/g, '←')
    .replace(/\$\\Rightarrow\$/g, '⇒')
    .replace(/\\Rightarrow/g, '⇒')
    .replace(/\$\\Leftarrow\$/g, '⇐')
    .replace(/\\Leftarrow/g, '⇐')
}

export default function ChatPage() {
  const navigate = useNavigate()

  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSession, setActiveSession] = useState<Session | null>(null)
  const [messages, setMessages] = useState<Message[]>([])

  // ── Session-storage helpers ───────────────────────────────────────────────
  // Key is scoped to the session ID so switching sessions doesn't mix up chat.
  const storageKey = (sid: string) => `chat_messages_${sid}`

  const persistMessages = useCallback((msgs: Message[], sid: string) => {
    try {
      sessionStorage.setItem(storageKey(sid), JSON.stringify(msgs))
    } catch { /* quota exceeded or private mode */ }
  }, [])

  const restoreMessages = useCallback((sid: string): Message[] => {
    try {
      const raw = sessionStorage.getItem(storageKey(sid))
      if (!raw) return []
      // Return as-is — streaming: true is preserved intentionally.
      // startReconnectPolling will resolve the in-flight message.
      return JSON.parse(raw) as Message[]
    } catch { return [] }
  }, [])

  // ── Reconnect polling ─────────────────────────────────────────────────────
  // When the user refreshes mid-stream we keep streaming:true and poll the DB
  // every 2s until the ADK backend saves the complete response to Postgres.
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const reconnectAttemptedRef = useRef(false)

  const stopPolling = useCallback(() => {
    if (pollingRef.current !== null) {
      clearInterval(pollingRef.current)
      pollingRef.current = null
    }
  }, [])

  const startReconnectPolling = useCallback(
    (userId: string, sessionId: string, restoredMsgs: Message[]) => {
      // Find the agent message that was still streaming at refresh time
      const streamingIdx = restoredMsgs.findIndex(
        (m) => m.streaming && m.role === 'agent'
      )
      if (streamingIdx === -1) return
      const streamingId = restoredMsgs[streamingIdx].id

      // Find the corresponding user query text for this turn
      const userMsg = [...restoredMsgs.slice(0, streamingIdx)]
        .reverse()
        .find((m) => m.role === 'user')
      const userMsgText = userMsg?.text

      // Helper: apply resolved message to state + storage
      const resolveWith = (text: string, sess?: Session) => {
        stopPolling()
        setMessages((prev) => {
          const next = prev.map((m) =>
            m.id === streamingId
              ? { ...m, text, streaming: false, steps: undefined }
              : m
          )
          persistMessages(next, sessionId)
          return next
        })
        setStreaming(false)
        if (sess) {
          setSessions((prev) => prev.map((s) => (s.id === sess.id ? sess : s)))
          setActiveSession((curr) => (curr?.id === sess.id ? sess : curr))
        }
      }

      // Count user messages in cached state — we need DB to have at least this many
      // to know the agent saw the latest query (not a response from a previous turn)
      const expectedUserCount = restoredMsgs.filter((m) => m.role === 'user').length

      // Returns true if DB already has a response for the latest user query
      const checkDB = async (): Promise<boolean> => {
        try {
          const sess = await getSession(userId, sessionId)
          if (!sess) return false
          const dbMsgs = parseEventsToMessages(sess.events ?? [])
          const dbUserCount = dbMsgs.filter((m) => m.role === 'user').length
          if (dbUserCount < expectedUserCount) return false

          // The last message in DB MUST be an agent message.
          const lastMsg = dbMsgs[dbMsgs.length - 1]
          if (lastMsg && lastMsg.role === 'agent' && lastMsg.text.trim()) {
            resolveWith(lastMsg.text, sess)
            return true
          }
        } catch { /* fall through */ }
        return false
      }

      // 1. Check DB immediately (in case agent completed right as refresh occurred)
      checkDB().then(async (resolved) => {
        if (resolved) return

        // Wait 2.5s and check DB once more
        await new Promise((r) => setTimeout(r, 2500))
        const resolvedOnSecondCheck = await checkDB()
        if (resolvedOnSecondCheck) return

        // 2. If DB still doesn't have an answer, ADK was cancelled on disconnect.
        // Automatically re-trigger runSse() for the user query so streaming resumes live!
        if (userMsgText) {
          setStreaming(true)
          abortRef.current = runSse(
            userId,
            sessionId,
            userMsgText,
            (token) => {
              setMessages((prev) => {
                const next = prev.map((m) =>
                  m.id === streamingId
                    ? { ...m, text: m.text + token }
                    : m
                )
                persistMessages(next, sessionId)
                return next
              })
            },
            () => {
              setMessages((prev) => {
                const next = prev.map((m) => {
                  if (m.id !== streamingId) return m
                  return { ...m, streaming: false, steps: undefined }
                })
                persistMessages(next, sessionId)
                return next
              })
              setStreaming(false)
            },
            (err) => {
              setMessages((prev) => {
                const next = prev.map((m) =>
                  m.id === streamingId
                    ? { ...m, text: `⚠️ Error: ${err.message}`, streaming: false, steps: undefined }
                    : m
                )
                persistMessages(next, sessionId)
                return next
              })
              setStreaming(false)
            },
            (stepDesc) => {
              setMessages((prev) => {
                const next = prev.map((m) => {
                  if (m.id !== streamingId) return m
                  const existing = m.steps || []
                  if (existing.includes(stepDesc)) return m
                  return { ...m, steps: [...existing, stepDesc] }
                })
                persistMessages(next, sessionId)
                return next
              })
            }
          )
        } else {
          resolveWith('⚠️ Stream disconnected. Please try asking your query again.')
        }
      })
    },
    [stopPolling, persistMessages]
  )

  // Stable ref so the init useEffect doesn't re-run when the callback identity changes
  const startReconnectPollingRef = useRef(startReconnectPolling)
  startReconnectPollingRef.current = startReconnectPolling

  const [input, setInputState] = useState(() => {
    try {
      return sessionStorage.getItem('chat_input_draft') || ''
    } catch {
      return ''
    }
  })

  const updateInput = useCallback((val: string) => {
    setInputState(val)
    try {
      if (val) {
        sessionStorage.setItem('chat_input_draft', val)
      } else {
        sessionStorage.removeItem('chat_input_draft')
      }
    } catch {}
  }, [])

  const [streaming, setStreaming] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [bannerDismissed, setBannerDismissed] = useState(() => {
    try {
      return localStorage.getItem('hide_github_banner') === 'true'
    } catch {
      return false
    }
  })

  const dismissBanner = () => {
    setBannerDismissed(true)
    try {
      localStorage.setItem('hide_github_banner', 'true')
    } catch {}
  }

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)

  const scrollBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  // Auth check + initial data
  useEffect(() => {
    let currentUser: UserProfile | null = null
    getMe()
      .then((p) => {
        if (!p) { navigate('/login'); return null }
        setProfile(p)
        currentUser = p
        return listSessions(p.user_id)
      })
      .then(async (s) => {
        if (s && s.length > 0 && currentUser) {
          setSessions(s)
          // Automatically select and load the most recent session
          const active = await getSession(currentUser.user_id, s[0].id)
          if (active) {
            setActiveSession(active)
            // Prefer sessionStorage — it has optimistic messages + steps.
            // Fall back to DB-parsed events if nothing is cached.
            const cached = restoreMessages(active.id)
            const hasStreaming = cached.some((m) => m.streaming)
            setMessages(
              cached.length > 0
                ? cached
                : parseEventsToMessages(active.events ?? [])
            )
            if (hasStreaming && currentUser && !reconnectAttemptedRef.current) {
              // Page was refreshed mid-stream — restore the loading state and
              // poll DB until the ADK backend saves the final response.
              reconnectAttemptedRef.current = true
              setStreaming(true)
              startReconnectPollingRef.current(currentUser.user_id, active.id, cached)
            }
          }
          // Fetch full session details for top sessions in parallel so sidebar displays real titles immediately
          const fullSessions = await Promise.all(
            s.slice(0, 20).map((item) =>
              item.id === s[0].id && active
                ? Promise.resolve(active)
                : getSession(currentUser!.user_id, item.id).catch(() => item)
            )
          )
          setSessions((prev) =>
            prev.map((orig) => {
              const found = fullSessions.find((f) => f && f.id === orig.id)
              return (found as Session) || orig
            })
          )
        } else if (currentUser) {
          // Brand new user with 0 sessions — auto-create initial session
          try {
            const ns = await createSession(currentUser.user_id)
            setSessions([ns])
            setActiveSession(ns)
            setMessages([])
          } catch { /* will create on first message */ }
        }
      })
      .catch(() => navigate('/login'))
      .finally(() => setLoading(false))
    return () => stopPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate])

  useEffect(() => { scrollBottom() }, [messages, scrollBottom])

  const handleNewChat = async () => {
    if (!profile) return
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setSidebarOpen(false)
    }
    try {
      const session = await createSession(profile.user_id)
      setSessions((prev) => [session, ...prev])
      setActiveSession(session)
      setMessages([])
      setTimeout(() => inputRef.current?.focus(), 50)
    } catch (e) {
      console.error('Failed to create session', e)
    }
  }

  const handleSelectSession = async (session: Session) => {
    if (!profile) return
    if (session.id === activeSession?.id) return

    setActiveSession(session)
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setSidebarOpen(false)
    }
    try {
      const fullSession = await getSession(profile.user_id, session.id)
      if (fullSession) {
        setMessages(parseEventsToMessages(fullSession.events ?? []))
        setSessions((prev) => prev.map((s) => (s.id === fullSession.id ? fullSession : s)))
      }
    } catch (e) {
      console.error('Failed to fetch session history', e)
    }
  }

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    if (!profile) return

    const remaining = sessions.filter((s) => s.id !== sessionId)
    setSessions(remaining)

    if (activeSession?.id === sessionId) {
      if (remaining.length > 0) {
        handleSelectSession(remaining[0])
      } else {
        try {
          const newSession = await createSession(profile.user_id)
          setSessions([newSession])
          setActiveSession(newSession)
          setMessages([])
        } catch (err) {
          setActiveSession(null)
          setMessages([])
        }
      }
    }

    try {
      await deleteSession(profile.user_id, sessionId)
    } catch (err) {
      console.error('Failed to delete session', err)
    }
  }

  const handleSend = async () => {
    if (!input.trim() || streaming || !profile) return

    let session = activeSession
    if (!session) {
      try { session = await createSession(profile.user_id) }
      catch { return }
      setSessions((prev) => [session!, ...prev])
      setActiveSession(session)
    }

    const currentSessionId = session.id
    const userMsgText = input.trim()

    const userMsg: Message = {
      id: Date.now().toString(),
      role: 'user',
      text: userMsgText,
    }
    const agentMsg: Message = {
      id: (Date.now() + 1).toString(),
      role: 'agent',
      text: '',
      streaming: true,
      steps: ['⚡ Processing query...'],
    }

    reconnectAttemptedRef.current = false
    setMessages((prev) => {
      const next = [...prev, userMsg, agentMsg]
      persistMessages(next, currentSessionId)
      return next
    })
    updateInput('')
    setStreaming(true)

    // Optimistically update session title in sidebar with user's first message if new
    setSessions((prev) =>
      prev.map((s) => {
        if (s.id === currentSessionId && (!s.events || s.events.length === 0)) {
          const updatedEvents = [{ author: 'user', content: { role: 'user', parts: [{ text: userMsgText }] } }]
          return { ...s, events: updatedEvents }
        }
        return s
      })
    )

    abortRef.current = runSse(
      profile.user_id,
      currentSessionId,
      userMsg.text,
      (token) => {
        setMessages((prev) => {
          const next = prev.map((m) =>
            m.id === agentMsg.id
              ? { ...m, text: m.text + token }
              : m
          )
          persistMessages(next, currentSessionId)
          return next
        })
      },

      () => {
        setMessages((prev) => {
          const next = prev.map((m) => {
            if (m.id !== agentMsg.id) return m
            return { ...m, streaming: false, steps: undefined }
          })
          persistMessages(next, currentSessionId)
          return next
        })
        setStreaming(false)
        // Background sync with database to ensure session.events is 100% updated with Postgres
        setTimeout(() => {
          if (profile && currentSessionId) {
            getSession(profile.user_id, currentSessionId).then((synced) => {
              if (synced) {
                setSessions((prev) => prev.map((s) => (s.id === synced.id ? synced : s)))
                setActiveSession((curr) => (curr?.id === synced.id ? synced : curr))
              }
            })
          }
        }, 1200)
      },
      (err) => {
        setMessages((prev) => {
          const next = prev.map((m) =>
            m.id === agentMsg.id
              ? { ...m, text: `⚠️ Error: ${err.message}`, streaming: false, steps: undefined }
              : m
          )
          persistMessages(next, currentSessionId)
          return next
        })
        setStreaming(false)
      },
      (stepDesc) => {
        setMessages((prev) => {
          const next = prev.map((m) => {
            if (m.id !== agentMsg.id) return m
            const existing = m.steps || []
            if (existing.includes(stepDesc)) return m
            return { ...m, steps: [...existing, stepDesc] }
          })
          persistMessages(next, currentSessionId)
          return next
        })
      }
    )
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const googleConnected = !!profile?.connected_providers?.google?.connected
  const googleUsername = profile?.connected_providers?.google?.username
  const googleMissingWrite = (profile?.connected_providers?.google?.missing_scopes ?? []).length > 0
  const githubConnected = !!profile?.connected_providers?.github?.connected
  const githubUsername = profile?.connected_providers?.github?.username

  if (loading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div className="spinner" />
      </div>
    )
  }

  return (
    <div className="app-shell">
      {/* Mobile Drawer Backdrop */}
      {sidebarOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <div className="sidebar-brand-left">
              <div className="sidebar-brand-icon">🤖</div>
              <span className="sidebar-brand-name">Workspace</span>
            </div>
            <button
              className="sidebar-toggle-btn"
              onClick={() => setSidebarOpen(false)}
              title="Close sidebar"
              id="close-sidebar-btn"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <button className="btn sidebar-new-btn" onClick={handleNewChat} id="new-chat-btn">
            <span style={{ fontSize: 16 }}>＋</span> New Chat
          </button>
        </div>

        <div className="sidebar-section-label">Recent Chats</div>

        <div className="sidebar-sessions">
          {sessions.length === 0 && (
            <div style={{ padding: '20px 12px', textAlign: 'center', fontSize: 13, color: 'var(--text-muted)' }}>
              No chats yet. Start a new one!
            </div>
          )}
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`session-item ${activeSession?.id === s.id ? 'active' : ''}`}
              onClick={() => handleSelectSession(s)}
            >
              <div className="session-item-content">
                <div className="session-item-title">{formatSessionTitle(s)}</div>
                <div className="session-item-meta">{formatTime(s.id)}</div>
              </div>
              <button
                className="session-item-delete"
                onClick={(e) => handleDeleteSession(e, s.id)}
                title="Delete chat"
                aria-label="Delete chat"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <polyline points="3 6 5 6 21 6"/>
                  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                  <line x1="10" y1="11" x2="10" y2="17"/>
                  <line x1="14" y1="11" x2="14" y2="17"/>
                </svg>
              </button>
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="sidebar-user" onClick={() => navigate('/settings')} id="settings-link">
            <div className="sidebar-avatar">
              {profile?.email?.[0]?.toUpperCase() ?? '?'}
            </div>
            <div className="sidebar-user-info">
              <div className="sidebar-user-email">{profile?.email ?? 'Unknown'}</div>
              <div className="sidebar-user-role">Workspace owner</div>
            </div>
            <div title="Settings" style={{ fontSize: 14, color: 'var(--text-muted)' }}>⚙️</div>
          </div>
        </div>
      </aside>

      {/* Main Chat Area */}
      <main className="chat-area">
        <div className="chat-topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0, flex: 1 }}>
            <button
              className="sidebar-toggle-btn topbar-toggle-btn"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title={sidebarOpen ? "Close sidebar" : "Open chats"}
              id="open-sidebar-btn"
              style={{
                border: '1px solid var(--border)',
                background: 'var(--bg-surface)',
                padding: '7px 8px',
                borderRadius: 'var(--radius-sm)',
                flexShrink: 0
              }}
            >
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="3" y1="12" x2="21" y2="12" />
                <line x1="3" y1="6" x2="21" y2="6" />
                <line x1="3" y1="18" x2="21" y2="18" />
              </svg>
            </button>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="chat-topbar-title">
                {activeSession ? formatSessionTitle(activeSession) : 'Workspace Agent'}
              </div>
              <div className="chat-topbar-meta">
                {activeSession
                  ? (activeSession.events?.length ? `Session ${activeSession.id.slice(0, 8)}...` : 'Ready to chat')
                  : 'Start a new conversation'}
              </div>
            </div>
          </div>
          <div className="chat-topbar-actions">
            <div className="topbar-provider-pills">
              <div
                className={`provider-pill ${googleConnected ? 'connected' : ''}`}
                title={googleConnected ? `Google: ${googleUsername || 'Connected'}` : 'Google: Not Connected'}
              >
                <span className={`provider-pill-dot ${googleConnected ? 'active' : ''}`} />
                <span>Google</span>
                {googleMissingWrite && <span style={{ fontSize: 10, color: '#f59e0b' }} title="Missing Write Permissions">⚠️</span>}
              </div>

              <div
                className={`provider-pill ${githubConnected ? 'connected' : ''}`}
                title={githubConnected ? `GitHub: @${githubUsername || 'Connected'}` : 'GitHub: Not Connected'}
              >
                <span className={`provider-pill-dot ${githubConnected ? 'active' : ''}`} />
                <span>GitHub</span>
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate('/settings')} id="topbar-settings-btn">
              ⚙️ <span className="settings-btn-label">Settings</span>
            </button>
          </div>
        </div>

        {/* GitHub connect banner */}
        {!githubConnected && !bannerDismissed && (
          <div className="github-banner">
            <span style={{ fontSize: 20 }}>🐙</span>
            <div className="github-banner-text">
              <strong>Connect GitHub to unlock all tools</strong>
              <span>Browse repos, issues, and pull requests with the agent</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <a href={getGitHubConnectUrl()} className="btn btn-ghost btn-sm" id="connect-github-banner-btn">
                Connect GitHub →
              </a>
              <button
                type="button"
                onClick={dismissBanner}
                className="btn btn-ghost btn-icon"
                title="Dismiss banner"
                aria-label="Dismiss banner"
                style={{
                  color: 'var(--text-muted)',
                  fontSize: 16,
                  padding: '4px 8px',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center'
                }}
              >
                ✕
              </button>
            </div>
          </div>
        )}

        {/* Messages */}
        <div className="messages">
          {messages.length === 0 && (
            <div className="messages-empty">
              <div className="messages-empty-icon">💬</div>
              <h3>How can I help you today?</h3>
              <p>Ask me to read your emails, search calendar events, or check GitHub repositories.</p>

              <div className="prompt-chips">
                <button
                  className="prompt-chip"
                  onClick={() => updateInput('Summarise my last 3 emails')}
                >
                  <span>📧</span> Summarise last 3 emails
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => updateInput('Search my unread emails and show sender details')}
                >
                  <span>🔍</span> Search unread emails
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => updateInput('Search my calendar events for this week')}
                >
                  <span>📅</span> Search events this week
                </button>
                <button
                  className="prompt-chip"
                  onClick={() => updateInput('List my recent GitHub repositories and issues')}
                >
                  <span>🐙</span> List my GitHub repos
                </button>
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={`message-row ${msg.role}`}>
              <div className={`message-avatar ${msg.role}`}>
                {msg.role === 'agent' ? '🤖' : (profile?.email?.[0]?.toUpperCase() ?? '?')}
              </div>
              <div className="message-body">
                <div className="message-name">
                  {msg.role === 'agent' ? 'Workspace Agent' : 'You'}
                </div>
                <div className={`message-bubble ${msg.role}`}>
                  {msg.role === 'agent' ? (
                    <>
                      {/* Option 3: Show only the LATEST step while agent is working,
                          before any response text has arrived. Disappears the moment
                          the first response token streams in. */}
                      {msg.streaming && !msg.text && msg.steps && msg.steps.length > 0 && (
                        <div className="agent-step-status">
                          <span className="agent-step-spinner" />
                          <span className="agent-step-label">
                            {msg.steps[msg.steps.length - 1]}
                          </span>
                        </div>
                      )}

                      {/* Typing dots before any step is known */}
                      {msg.streaming && !msg.text && (!msg.steps || msg.steps.length === 0) && (
                        <div className="typing-dots">
                          <span /><span /><span />
                        </div>
                      )}

                      {/* Response */}
                      {msg.text && (
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                          {cleanMarkdownText(msg.text)}
                        </ReactMarkdown>
                      )}

                      {/* Interactive Auth Action Card */}
                      {msg.text && (() => {
                        const card = getAuthCardInfo(msg.text)
                        if (!card) return null

                        // Guard: do not show GitHub card if GitHub is already connected
                        if (card.type === 'github' && githubConnected) return null

                        // Guard: do not show Google card if Google is already connected with write scopes
                        if (card.type === 'google' && googleConnected && !googleMissingWrite) return null

                        return (
                          <div className="auth-action-card">
                            <div className="auth-action-card-info">
                              <span style={{ fontSize: 20 }}>🔑</span>
                              <div>
                                <div className="auth-action-card-title">{card.label}</div>
                                <div className="auth-action-card-desc">
                                  {card.type === 'google'
                                    ? 'Grant required permissions to execute this workspace action.'
                                    : 'Connect your GitHub account to access repositories and issues.'}
                                </div>
                              </div>
                            </div>
                            <a
                              href={card.type === 'google' ? getGoogleReauthUrl() : getGitHubConnectUrl()}
                              className="btn btn-primary btn-sm"
                              style={{ textDecoration: 'none', whiteSpace: 'nowrap' }}
                            >
                              {card.type === 'google' ? 'Re-authorize Google →' : 'Connect GitHub →'}
                            </a>
                          </div>
                        )
                      })()}
                    </>
                  ) : (
                    msg.text
                  )}
                </div>
              </div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>

        {/* Input */}
        <div className="input-area">
          <div className="input-wrapper">
            <textarea
              ref={inputRef}
              className="message-input"
              placeholder="Ask about your emails, calendar, or GitHub..."
              value={input}
              onChange={(e) => updateInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={streaming}
              id="message-input"
            />
            <button
              className="send-btn"
              onClick={handleSend}
              disabled={!input.trim() || streaming}
              id="send-btn"
              title="Send (Enter)"
            >
              {streaming
                ? <div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} />
                : <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="22" y1="2" x2="11" y2="13"/>
                    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                  </svg>
              }
            </button>
          </div>
          <div className="input-hint">Press Enter to send · Shift+Enter for new line</div>
        </div>
      </main>
    </div>
  )
}
