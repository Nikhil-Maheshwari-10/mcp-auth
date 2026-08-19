import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import WorkspaceSwitcher from '../components/WorkspaceSwitcher'
import {
  UserProfile,
  Session,
  getMe,
  listSessions,
  createSession,
  getSession,
  deleteSession,
  runSse,
  logout,
  getGitHubConnectUrl,
  getGitHubAddAccountUrl,
  getGoogleReauthUrl,
  getGoogleAddAccountUrl,
  removeGoogleAccount,
  disconnectGitHub,
  createWorkspace,
  formatErrorMessage,
} from '../lib/api'

interface Message {
  id: string
  role: 'user' | 'agent'
  text: string
  streaming?: boolean
  steps?: string[]
  isError?: boolean
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
                  const text = m.text.trim()
                    ? m.text
                    : '⚠️ The AI model did not return a response. Please try asking your question again.'
                  return {
                    ...m,
                    text,
                    isError: !m.text.trim(),
                    streaming: false,
                    steps: undefined,
                  }
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
                    ? { ...m, text: formatErrorMessage(err), isError: true, streaming: false, steps: undefined }
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
  const [addBtnHovered, setAddBtnHovered] = useState(false)
  const [bannerDismissed, setBannerDismissed] = useState(() => {
    try {
      return localStorage.getItem('hide_github_banner') === 'true'
    } catch {
      return false
    }
  })

  // Modal states
  const [showProfileModal, setShowProfileModal] = useState(false)
  const [showSignoutModal, setShowSignoutModal] = useState(false)
  const [signingOut, setSigningOut] = useState(false)
  const [removingAccountId, setRemovingAccountId] = useState<string | null>(null)
  const [disconnectingGitHub, setDisconnectingGitHub] = useState(false)

  // Create Workspace Modal State
  const [showCreateWsModal, setShowCreateWsModal] = useState(false)
  const [createWsIntent, setCreateWsIntent] = useState<'switch' | 'add-account' | 'add-account-google' | 'add-account-github'>('switch')
  const [newWsName, setNewWsName] = useState('')
  const [creatingWs, setCreatingWs] = useState(false)

  const handleOpenCreateWsModal = (intent: 'switch' | 'add-account' | 'add-account-google' | 'add-account-github' = 'switch') => {
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
        if (createWsIntent === 'add-account-github') {
          window.location.href = getGitHubAddAccountUrl()
        } else if (createWsIntent === 'add-account' || createWsIntent === 'add-account-google') {
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

  const handleRemoveAccount = async (accountId: string) => {
    setRemovingAccountId(accountId)
    const success = await removeGoogleAccount(accountId)
    if (success) {
      const updated = await getMe()
      if (updated) setProfile(updated)
    }
    setRemovingAccountId(null)
  }

  const handleDisconnectGitHub = async (providerAccountId?: string) => {
    setDisconnectingGitHub(true)
    const success = await disconnectGitHub(providerAccountId)
    if (success) {
      const updated = await getMe()
      if (updated) setProfile(updated)
    }
    setDisconnectingGitHub(false)
  }

  const dismissBanner = () => {
    setBannerDismissed(true)
    try {
      localStorage.setItem('hide_github_banner', 'true')
    } catch {}
  }

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const abortRef = useRef<AbortController | null>(null)
  const sessionCreatingRef = useRef(false)

  // Auto-focus chat input when user starts typing anywhere on the page
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent) => {
      // Ignore if already focused on an input/textarea/select/contenteditable
      const active = document.activeElement
      if (
        active instanceof HTMLInputElement ||
        active instanceof HTMLTextAreaElement ||
        active instanceof HTMLSelectElement ||
        (active instanceof HTMLElement && active.isContentEditable)
      ) return

      // Ignore modifier-only combos (Ctrl+C, Cmd+V, etc.) and special keys
      if (e.ctrlKey || e.metaKey || e.altKey) return
      if (e.key.length !== 1) return  // ignore Escape, F1-F12, ArrowKeys, etc.

      // Focus the textarea and let the keypress land naturally
      const ta = inputRef.current
      if (!ta) return
      ta.focus()
      // The browser will append the character to the now-focused textarea automatically
    }

    window.addEventListener('keydown', handleGlobalKeyDown)
    return () => window.removeEventListener('keydown', handleGlobalKeyDown)
  }, [])

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
        return listSessions(p.workspace_id || p.user_id)
      })
      .then(async (s) => {
        if (s && s.length > 0 && currentUser) {
          const targetId = currentUser.workspace_id || currentUser.user_id

          // Deduplicate / cleanup empty sessions from ADK list
          const emptySessions = s.filter((item) => !item.events || item.events.length === 0)
          let cleanedSessions = s
          if (emptySessions.length > 1) {
            const keepEmpty = emptySessions[0]
            const toDelete = emptySessions.slice(1)
            for (const dup of toDelete) {
              deleteSession(targetId, dup.id).catch(() => {})
            }
            const deleteIds = new Set(toDelete.map((d) => d.id))
            cleanedSessions = s.filter((item) => !deleteIds.has(item.id))
          }

          setSessions(cleanedSessions)
          const active = await getSession(targetId, cleanedSessions[0].id)
          if (active) {
            setActiveSession(active)
            const cached = restoreMessages(active.id)
            const hasStreaming = cached.some((m) => m.streaming)
            setMessages(
              cached.length > 0
                ? cached
                : parseEventsToMessages(active.events ?? [])
            )
            if (hasStreaming && currentUser && !reconnectAttemptedRef.current) {
              reconnectAttemptedRef.current = true
              setStreaming(true)
              startReconnectPollingRef.current(targetId, active.id, cached)
            }
          }
          const fullSessions = await Promise.all(
            cleanedSessions.slice(0, 20).map((item) =>
              item.id === cleanedSessions[0].id && active
                ? Promise.resolve(active)
                : getSession(targetId, item.id).catch(() => item)
            )
          )
          setSessions((prev) =>
            prev.map((orig) => {
              const found = fullSessions.find((f) => f && f.id === orig.id)
              return (found as Session) || orig
            })
          )
        } else if (currentUser && !sessionCreatingRef.current) {
          sessionCreatingRef.current = true
          try {
            const ns = await createSession(currentUser.workspace_id || currentUser.user_id)
            setSessions([ns])
            setActiveSession(ns)
            setMessages([])
          } catch { /* will create on first message */ }
          finally {
            sessionCreatingRef.current = false
          }
        }
      })
      .catch(() => navigate('/login'))
      .finally(() => setLoading(false))
    return () => stopPolling()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navigate])

  useEffect(() => { scrollBottom() }, [messages, scrollBottom])

  const handleNewChat = async () => {
    if (!profile || sessionCreatingRef.current) return
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      setSidebarOpen(false)
    }

    // Do not create a new session if the current active session is already empty
    if (messages.length === 0 && activeSession) {
      setTimeout(() => inputRef.current?.focus(), 50)
      return
    }

    // Do not create a new session if the top session in history has no events
    const topSession = sessions[0]
    if (topSession && (!topSession.events || topSession.events.length === 0)) {
      handleSelectSession(topSession)
      setTimeout(() => inputRef.current?.focus(), 50)
      return
    }

    sessionCreatingRef.current = true
    try {
      const targetId = profile.workspace_id || profile.user_id
      const session = await createSession(targetId)
      setSessions((prev) => [session, ...prev])
      setActiveSession(session)
      setMessages([])
      setTimeout(() => inputRef.current?.focus(), 50)
    } catch (e) {
      console.error('Failed to create session', e)
    } finally {
      sessionCreatingRef.current = false
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
      const targetId = profile.workspace_id || profile.user_id
      const fullSession = await getSession(targetId, session.id)
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
    const targetId = profile.workspace_id || profile.user_id

    if (activeSession?.id === sessionId) {
      if (remaining.length > 0) {
        handleSelectSession(remaining[0])
      } else {
        try {
          const newSession = await createSession(targetId)
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
      await deleteSession(targetId, sessionId)
    } catch (err) {
      console.error('Failed to delete session', err)
    }
  }

  const handleSend = async () => {
    if (!input.trim() || streaming || !profile) return
    const targetId = profile.workspace_id || profile.user_id

    let session = activeSession
    if (!session) {
      try { session = await createSession(targetId) }
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
      targetId,
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
            const text = m.text.trim()
              ? m.text
              : '⚠️ The AI model did not return a response. Please try asking your question again.'
            return {
              ...m,
              text,
              isError: !m.text.trim(),
              streaming: false,
              steps: undefined,
            }
          })
          persistMessages(next, currentSessionId)
          return next
        })
        setStreaming(false)
        setTimeout(() => {
          if (profile && currentSessionId) {
            getSession(targetId, currentSessionId).then((synced) => {
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
              ? { ...m, text: formatErrorMessage(err), isError: true, streaming: false, steps: undefined }
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
  const googleAccounts = profile?.connected_providers?.google?.accounts ?? []
  const sortedGoogleAccounts = useMemo(() => {
    const list = googleAccounts.length > 0 ? [...googleAccounts] : []
    const ownerEmail = profile?.email
    return list.sort((a, b) => {
      if (a.email === ownerEmail) return -1
      if (b.email === ownerEmail) return 1
      return 0
    })
  }, [googleAccounts, profile?.email])
  const primaryAccount = sortedGoogleAccounts.find((a: any) => a.email === profile?.email) ?? sortedGoogleAccounts[0]
  const primaryAvatarUrl = primaryAccount?.avatar_url ?? sortedGoogleAccounts.find((a: any) => a.avatar_url)?.avatar_url ?? null
  const googleMissingWrite = (profile?.connected_providers?.google?.missing_scopes ?? []).length > 0
  const githubConnected = !!profile?.connected_providers?.github?.connected
  const githubUsername = profile?.connected_providers?.github?.username
  const githubAccounts: Array<{ username: string; provider_account_id: string; is_active: boolean; avatar_url?: string | null }> =
    profile?.connected_providers?.github?.accounts ?? []

  // Account limits from /me response
  const maxGmail = profile?.account_limits?.max_gmail_accounts ?? 3
  const maxGithub = profile?.account_limits?.max_github_accounts ?? 3
  const atGmailLimit = googleAccounts.length >= maxGmail
  const atGithubLimit = githubAccounts.length >= maxGithub

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
          {/* Workspace Switcher or + Create Workspace button above user profile */}
          {profile && (profile.workspace_id || (profile.workspaces && profile.workspaces.length > 0)) ? (
            <div style={{ padding: '0 12px 8px 12px' }}>
              <WorkspaceSwitcher
                currentWorkspaceId={profile.workspace_id}
                currentWorkspaceName={profile.workspace_name}
              />
            </div>
          ) : (
            <div style={{ padding: '0 12px 8px 12px' }}>
              <button
                type="button"
                className="sidebar-create-ws-btn"
                onClick={() => handleOpenCreateWsModal('switch')}
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
                <span>Create Workspace</span>
              </button>
            </div>
          )}

          <div className="sidebar-user-wrapper" style={{ position: 'relative' }}>
            {/* Glassmorphic Accounts Popover on hover — only when multiple accounts & not hovering + Add */}
            {(googleAccounts.length + (githubConnected ? 1 : 0)) > 1 && !addBtnHovered && (
              <div className="accounts-popover">
                <div className="popover-header">
                  <span>Connected Accounts</span>
                  <span className="popover-badge">{(googleAccounts.length || 1) + (githubAccounts.length || (githubConnected ? 1 : 0))}</span>
                </div>

                <div className="popover-accounts-list">
                  {(googleAccounts.length > 0
                    ? googleAccounts
                    : [{ email: profile?.email ?? 'Connected Account', provider_account_id: 'primary', is_active: true, avatar_url: null }]
                  ).map((acc) => (
                    <div key={acc.provider_account_id} className="popover-account-item">
                      <div className="popover-account-avatar">
                        {acc.avatar_url ? (
                          <img
                            src={acc.avatar_url}
                            alt={acc.email}
                            className="popover-avatar-img"
                            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; (e.target as HTMLImageElement).nextElementSibling?.setAttribute('style', 'display:flex'); }}
                          />
                        ) : null}
                        <div className="popover-avatar-fallback" style={{ display: acc.avatar_url ? 'none' : 'flex' }}>
                          <svg width="14" height="14" viewBox="0 0 18 18">
                            <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/>
                            <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.72.48-1.63.77-2.7.77-2.07 0-3.82-1.4-4.45-3.28H1.87v2.07A8 8 0 0 0 8.98 17z"/>
                            <path fill="#FBBC05" d="M4.53 10.54A4.87 4.87 0 0 1 4.27 9c0-.53.09-1.05.26-1.54V5.39H1.87A8 8 0 0 0 .98 9c0 1.29.31 2.51.89 3.61l2.66-2.07z"/>
                            <path fill="#EA4335" d="M8.98 3.58c1.16 0 2.21.4 3.03 1.18l2.27-2.27A8 8 0 0 0 .98 9l2.85 2.07C4.3 5.07 6.35 3.58 8.98 3.58z"/>
                          </svg>
                        </div>
                      </div>
                      <div className="popover-account-details">
                        <div className="popover-account-email">{acc.email}</div>
                        <div className="popover-account-sub">
                          Gmail account
                        </div>
                      </div>
                    </div>
                  ))}

                  {githubAccounts.length > 0 ? (
                    githubAccounts.map((ghAcc) => (
                      <div key={ghAcc.provider_account_id} className="popover-account-item">
                        <div className="popover-account-avatar">
                          {ghAcc.avatar_url ? (
                            <img
                              src={ghAcc.avatar_url}
                              alt={ghAcc.username}
                              className="popover-avatar-img"
                              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; (e.target as HTMLImageElement).nextElementSibling?.setAttribute('style', 'display:flex'); }}
                            />
                          ) : null}
                          <div className="popover-avatar-fallback" style={{ display: ghAcc.avatar_url ? 'none' : 'flex', background: '#24292e' }}>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="#e6edf3">
                              <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
                            </svg>
                          </div>
                        </div>
                        <div className="popover-account-details">
                          <div className="popover-account-email">@{ghAcc.username}</div>
                          <div className="popover-account-sub">GitHub</div>
                        </div>
                      </div>
                    ))
                  ) : githubConnected && (
                    <div className="popover-account-item">
                      <div className="popover-account-avatar">
                        <div className="popover-avatar-fallback" style={{ display: 'flex', background: '#24292e' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="#e6edf3">
                            <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
                          </svg>
                        </div>
                      </div>
                      <div className="popover-account-details">
                        <div className="popover-account-email">@{githubUsername}</div>
                        <div className="popover-account-sub">GitHub</div>
                      </div>
                    </div>
                  )}
                </div>

                <div className="popover-footer" onClick={() => navigate('/settings')} style={{ cursor: 'pointer' }}>
                  <span>Manage in Settings</span>
                </div>
              </div>
            )}

            <div className="sidebar-user" onClick={() => setShowProfileModal(true)} id="profile-modal-trigger">
              {/* Avatar Stack for multi-account or single avatar */}
              <div style={{ display: 'flex', alignItems: 'center' }}>
                {sortedGoogleAccounts.length > 1 ? (
                  <div style={{ display: 'flex', alignItems: 'center' }}>
                    {sortedGoogleAccounts.slice(0, 3).map((acc: any, idx: number) => (
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
              <div className="sidebar-user-info" style={{ marginLeft: sortedGoogleAccounts.length > 1 ? 6 : 0, overflow: 'hidden' }}>
                <div className="sidebar-user-email" style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{profile?.email ?? 'Unknown'}</div>
                <div className="sidebar-user-role" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                  {sortedGoogleAccounts.length > 1 ? `● ${sortedGoogleAccounts.length} Connected Accounts` : 'Workspace owner'}
                </div>
              </div>

              {/* Show + Add Google Account button ONLY when switched to a workspace */}
              {profile?.workspace_id && (
                <button
                  type="button"
                  className="sidebar-add-account-btn"
                  title="Add Gmail Account to Workspace"
                  onMouseEnter={() => setAddBtnHovered(true)}
                  onMouseLeave={() => setAddBtnHovered(false)}
                  onClick={async (e) => {
                    e.stopPropagation()
                    window.location.href = getGoogleAddAccountUrl()
                  }}
                >
                  <svg width="12" height="12" viewBox="0 0 18 18">
                    <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/>
                    <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.72.48-1.63.77-2.7.77-2.07 0-3.82-1.4-4.45-3.28H1.87v2.07A8 8 0 0 0 8.98 17z"/>
                    <path fill="#FBBC05" d="M4.53 10.54A4.87 4.87 0 0 1 4.27 9c0-.53.09-1.05.26-1.54V5.39H1.87A8 8 0 0 0 .98 9c0 1.29.31 2.51.89 3.61l2.66-2.07z"/>
                    <path fill="#EA4335" d="M8.98 3.58c1.16 0 2.21.4 3.03 1.18l2.27-2.27A8 8 0 0 0 .98 9l2.85 2.07C4.3 5.07 6.35 3.58 8.98 3.58z"/>
                  </svg>
                  <span>+ Add</span>
                </button>
              )}
            </div>
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
                title={googleConnected ? `Google: ${googleAccounts.length > 1 ? `${googleAccounts.length} accounts connected` : (googleUsername || 'Connected')}` : 'Google: Not Connected'}
              >
                <span className={`provider-pill-dot ${googleConnected ? 'active' : ''}`} />
                <span>{googleAccounts.length > 1 ? `Google (${googleAccounts.length})` : 'Google'}</span>
                {googleMissingWrite && <span style={{ fontSize: 10, color: '#f59e0b' }} title="Missing Write Permissions">⚠️</span>}
              </div>

              <div
                className={`provider-pill ${githubConnected ? 'connected' : ''}`}
                title={githubConnected ? `GitHub: ${githubAccounts.length > 1 ? `${githubAccounts.length} accounts connected` : `@${githubUsername || 'Connected'}`}` : 'GitHub: Not Connected'}
              >
                <span className={`provider-pill-dot ${githubConnected ? 'active' : ''}`} />
                <span>{githubAccounts.length > 1 ? `GitHub (${githubAccounts.length})` : 'GitHub'}</span>
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
                  <span>📩</span> Summarise last 3 emails
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

                      {/* Retry Action Bar for Error / Interrupted Messages */}
                      {(msg.isError || (msg.text && (msg.text.startsWith('⚠️') || msg.text.startsWith('⚡') || msg.text.startsWith('🔌') || msg.text.startsWith('🌐')))) && !msg.streaming && (() => {
                        const msgIdx = messages.findIndex((m) => m.id === msg.id)
                        const prevUserMsg = msgIdx > 0 ? messages.slice(0, msgIdx).reverse().find((m) => m.role === 'user') : null
                        const queryToRetry = prevUserMsg?.text || ''

                        return (
                          <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8, flexWrap: 'wrap' }}>
                            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Something went wrong processing this request.</span>
                            {queryToRetry && (
                              <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                onClick={() => {
                                  updateInput(queryToRetry)
                                  setTimeout(() => {
                                    const sendBtn = document.getElementById('send-btn')
                                    sendBtn?.click()
                                  }, 100)
                                }}
                                style={{ fontSize: 12, padding: '4px 10px', color: '#818cf8', display: 'flex', alignItems: 'center', gap: 5, background: 'rgba(99, 102, 241, 0.1)', border: '1px solid rgba(99, 102, 241, 0.25)', borderRadius: 'var(--radius-md)' }}
                              >
                                🔄 Retry Query
                              </button>
                            )}
                          </div>
                        )
                      })()}

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

      {/* ─── Profile Management Modal ─────────────────────────────────────── */}
      {showProfileModal && (
        <div className="profile-modal-overlay" onClick={() => setShowProfileModal(false)}>
          <div className="profile-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="profile-modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 44, height: 44, borderRadius: '50%', overflow: 'hidden', border: '2px solid rgba(255,255,255,0.15)', background: 'rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  {primaryAvatarUrl ? (
                    <img src={primaryAvatarUrl} alt="User avatar" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  ) : (
                    <span style={{ fontSize: 20 }}>👤</span>
                  )}
                </div>
                <div>
                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 600, color: 'var(--text-primary)' }}>User Profile</h3>
                  <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>{profile?.email}</div>
                </div>
              </div>
              <button
                type="button"
                className="btn btn-ghost btn-sm btn-icon"
                onClick={() => setShowProfileModal(false)}
                style={{ width: 32, height: 32, borderRadius: '50%', fontSize: 16 }}
              >
                ✕
              </button>
            </div>

            <div className="profile-modal-body">
              {/* Primary Identity Info */}
              <div style={{ padding: '14px 16px', background: 'rgba(255,255,255,0.03)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div>
                    <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Primary Identity</div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)', marginTop: 2 }}>{profile?.email}</div>
                  </div>
                  <span className="badge badge-connected">✓ Authenticated</span>
                </div>
              </div>

              {/* Connected Google Accounts */}
              <div style={{ marginBottom: 20 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                    Google Accounts ({googleAccounts.length || 1})
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={atGmailLimit}
                    title={atGmailLimit ? `Gmail account limit reached (${maxGmail} max)` : 'Add another Gmail account'}
                    style={{ fontSize: 11, padding: '4px 10px', color: atGmailLimit ? 'var(--text-muted)' : '#60a5fa', cursor: atGmailLimit ? 'not-allowed' : 'pointer', opacity: atGmailLimit ? 0.5 : 1 }}
                    onClick={() => {
                      if (atGmailLimit) return
                      setShowProfileModal(false)
                      // Only prompt workspace creation when upgrading from single → multi-account
                      if (!profile?.workspace_id && googleAccounts.length > 0) {
                        handleOpenCreateWsModal('add-account-google')
                      } else {
                        window.location.href = getGoogleAddAccountUrl()
                      }
                    }}
                  >
                    {atGmailLimit ? `Gmail (${googleAccounts.length}/${maxGmail})` : '➕ Add Gmail Account'}
                  </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {sortedGoogleAccounts.map((acc: any) => {
                    const isOwner = acc.email === profile?.email
                    return (
                      <div
                        key={acc.provider_account_id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '10px 12px',
                          background: 'rgba(255,255,255,0.03)',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-md)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{ width: 28, height: 28, borderRadius: '50%', overflow: 'hidden', flexShrink: 0, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            {acc.avatar_url ? (
                              <img src={acc.avatar_url} alt={acc.email} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              <svg width="14" height="14" viewBox="0 0 18 18">
                                <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/>
                                <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.72.48-1.63.77-2.7.77-2.07 0-3.82-1.4-4.45-3.28H1.87v2.07A8 8 0 0 0 8.98 17z"/>
                                <path fill="#FBBC05" d="M4.53 10.54A4.87 4.87 0 0 1 4.27 9c0-.53.09-1.05.26-1.54V5.39H1.87A8 8 0 0 0 .98 9c0 1.29.31 2.51.89 3.61l2.66-2.07z"/>
                                <path fill="#EA4335" d="M8.98 3.58c1.16 0 2.21.4 3.03 1.18l2.27-2.27A8 8 0 0 0 .98 9l2.85 2.07C4.3 5.07 6.35 3.58 8.98 3.58z"/>
                              </svg>
                            )}
                          </div>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>
                              {acc.email}
                            </div>
                          </div>
                        </div>

                        {!isOwner && (
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm btn-disconnect-hover"
                            disabled={removingAccountId === acc.provider_account_id}
                            onClick={() => handleRemoveAccount(acc.provider_account_id)}
                            style={{ fontSize: 11, padding: '2px 8px' }}
                          >
                            {removingAccountId === acc.provider_account_id ? 'Removing...' : 'Remove'}
                          </button>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* GitHub Accounts Section */}
              <div style={{ marginBottom: 24 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                    GitHub Accounts ({githubAccounts.length || (githubConnected ? 1 : 0)})
                  </div>
                  {/* Only show Add button when at least 1 GitHub account is already connected */}
                  {(githubAccounts.length > 0 || githubConnected) && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={atGithubLimit}
                      title={atGithubLimit ? `GitHub account limit reached (${maxGithub} max)` : 'Add another GitHub account'}
                      style={{ fontSize: 11, padding: '4px 10px', color: atGithubLimit ? 'var(--text-muted)' : '#60a5fa', display: 'flex', alignItems: 'center', gap: 4, cursor: atGithubLimit ? 'not-allowed' : 'pointer', opacity: atGithubLimit ? 0.5 : 1 }}
                      onClick={() => {
                        if (atGithubLimit) return
                        setShowProfileModal(false)
                        if (!profile?.workspace_id) {
                          handleOpenCreateWsModal('add-account-github')
                        } else {
                          window.location.href = getGitHubAddAccountUrl()
                        }
                      }}
                    >
                      {atGithubLimit ? `GitHub (${githubAccounts.length}/${maxGithub})` : '➕ Add GitHub Account'}
                    </button>
                  )}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {githubAccounts.length > 0 ? (
                    githubAccounts.map((ghAcc) => (
                      <div
                        key={ghAcc.provider_account_id}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '10px 12px',
                          background: 'rgba(255,255,255,0.03)',
                          border: '1px solid var(--border)',
                          borderRadius: 'var(--radius-md)',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <div style={{ width: 28, height: 28, borderRadius: '50%', overflow: 'hidden', flexShrink: 0, border: '1px solid rgba(255,255,255,0.12)', background: '#24292e', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            {ghAcc.avatar_url ? (
                              <img src={ghAcc.avatar_url} alt={ghAcc.username} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                            ) : (
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="#e6edf3">
                                <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
                              </svg>
                            )}
                          </div>
                          <div>
                            <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>@{ghAcc.username}</div>
                          </div>
                        </div>

                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-disconnect-hover"
                          disabled={disconnectingGitHub}
                          onClick={() => handleDisconnectGitHub(ghAcc.provider_account_id)}
                          title="Disconnect this account"
                          style={{ fontSize: 11, padding: '2px 8px' }}
                        >
                          {disconnectingGitHub ? 'Removing...' : 'Disconnect'}
                        </button>
                      </div>
                    ))
                  ) : (
                    <div style={{ padding: '10px 12px', background: 'rgba(255,255,255,0.03)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <div style={{ width: 28, height: 28, borderRadius: '50%', overflow: 'hidden', flexShrink: 0, border: '1px solid rgba(255,255,255,0.12)', background: '#24292e', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="#e6edf3">
                            <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
                          </svg>
                        </div>
                        <div>
                          {githubConnected ? (
                            <>
                              <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>@{githubUsername}</div>
                              <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Connected · 12 Developer Tools</div>
                            </>
                          ) : (
                            <div style={{ fontSize: 13, color: 'var(--text-muted)' }}>Not Connected</div>
                          )}
                        </div>
                      </div>

                      {githubConnected ? (
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm btn-disconnect-hover"
                          onClick={() => handleDisconnectGitHub()}
                          disabled={disconnectingGitHub}
                          style={{ fontSize: 11, padding: '2px 8px' }}
                        >
                          {disconnectingGitHub ? 'Disconnecting...' : 'Disconnect'}
                        </button>
                      ) : (
                        <a href={getGitHubConnectUrl()} className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '2px 8px' }}>
                          Connect
                        </a>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* Footer Action Buttons */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingTop: 16, borderTop: '1px solid var(--border)' }}>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => { setShowProfileModal(false); navigate('/settings'); }}
                  style={{ display: 'flex', alignItems: 'center', gap: 6 }}
                >
                  ⚙️ Settings
                </button>

                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  onClick={() => { setShowProfileModal(false); setShowSignoutModal(true); }}
                >
                  🔴 Sign Out
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── Signout Confirmation Modal ────────────────────────────────────── */}
      {showSignoutModal && (
        <div className="profile-modal-overlay" onClick={() => setShowSignoutModal(false)}>
          <div className="profile-modal-card" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 440, width: '92vw', boxSizing: 'border-box' }}>
            <div style={{ padding: 'clamp(18px, 5vw, 24px)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
                <span style={{ fontSize: 'clamp(24px, 6vw, 32px)', flexShrink: 0, lineHeight: 1 }}>⚠️</span>
                <div>
                  <h3 style={{ margin: 0, fontSize: 'clamp(15px, 4vw, 17px)', fontWeight: 600, color: 'var(--text-primary)' }}>
                    Sign out ?
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
                  {signingOut ? 'Signing out...' : 'Sign Out'}
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
