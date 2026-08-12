/**
 * api.ts — Typed wrappers for all backend API calls.
 *
 * Base URL is proxied via Vite dev config (localhost:5173 → localhost:8001).
 * In production, nginx reverse-proxies /auth/ and /me to the api container.
 */

const API_BASE = '/api'
const ADK_BASE = '/apps'

export interface GoogleAccount {
  email: string
  provider_account_id: string
  is_active: boolean
  scopes: string
  missing_scopes: string[]
  connected: boolean
  avatar_url?: string | null
}

export interface Workspace {
  id: string
  name: string
  created_at: string
  role?: string
  account_count?: number
}

export interface UserProfile {
  user_id: string
  workspace_id: string
  workspace_name: string
  email: string | null
  connected_providers: {
    google?: {
      connected: boolean
      username: string | null
      scopes: string
      missing_scopes: string[]
      accounts?: GoogleAccount[]
    }
    github?: {
      connected: boolean
      username: string | null
      accounts?: Array<{
        username: string
        provider_account_id: string
        is_active: boolean
        avatar_url?: string | null
      }>
    }
  }
  workspaces?: Workspace[]
}

export interface Session {
  id: string
  app_name: string
  user_id: string
  state: Record<string, unknown>
  events?: ChatEvent[]
}

export interface ChatEvent {
  author: string
  content?: {
    parts?: { text?: string }[]
  }
  is_final_response?: boolean
}

// ─── Auth ────────────────────────────────────────────

export async function logout(resetWorkspace: boolean = false): Promise<void> {
  try {
    const url = `${API_BASE}/auth/logout${resetWorkspace ? '?reset_workspace=true' : ''}`
    await fetch(url, { method: 'POST', credentials: 'include' })
  } catch { /* ignore network error on logout */ }
}

export async function getMe(): Promise<UserProfile | null> {
  const res = await fetch(`${API_BASE}/me`, { credentials: 'include' })
  if (res.status === 401) return null
  if (!res.ok) throw new Error('Failed to fetch user profile')
  return res.json()
}

export function getGoogleLoginUrl(): string {
  return `${API_BASE}/auth/google/login`
}

export function getGoogleReauthUrl(accountEmail?: string): string {
  const base = `${API_BASE}/auth/google/reauth`
  return accountEmail ? `${base}?account_email=${encodeURIComponent(accountEmail)}` : base
}

export function getGoogleAddAccountUrl(): string {
  return `${API_BASE}/auth/google/add-account`
}

export async function removeGoogleAccount(providerAccountId: string): Promise<boolean> {
  try {
    const res = await fetch(
      `${API_BASE}/auth/google/remove-account?provider_account_id=${encodeURIComponent(providerAccountId)}`,
      { method: 'DELETE', credentials: 'include' }
    )
    return res.ok
  } catch {
    return false
  }
}

export async function setGoogleActiveAccount(providerAccountId: string): Promise<boolean> {
  try {
    const res = await fetch(
      `${API_BASE}/auth/google/set-active?provider_account_id=${encodeURIComponent(providerAccountId)}`,
      { method: 'POST', credentials: 'include' }
    )
    return res.ok
  } catch {
    return false
  }
}

export function getGitHubConnectUrl(): string {
  return `${API_BASE}/auth/github/login`
}

export function getGitHubAddAccountUrl(): string {
  return `${API_BASE}/auth/github/add-account`
}

export async function disconnectGitHub(providerAccountId?: string): Promise<boolean> {
  try {
    const url = providerAccountId
      ? `${API_BASE}/auth/github/remove-account?provider_account_id=${encodeURIComponent(providerAccountId)}`
      : `${API_BASE}/auth/github/disconnect`
    const res = await fetch(url, {
      method: providerAccountId ? 'DELETE' : 'POST',
      credentials: 'include',
    })
    return res.ok
  } catch {
    return false
  }
}

// ─── Workspaces ─────────────────────────────────────

export async function listWorkspaces(): Promise<Workspace[]> {
  try {
    const res = await fetch(`${API_BASE}/workspace/list`, { credentials: 'include' })
    if (!res.ok) return []
    return res.json()
  } catch {
    return []
  }
}

export async function switchWorkspace(workspaceId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/workspace/switch`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workspace_id: workspaceId }),
    })
    return res.ok
  } catch {
    return false
  }
}

export async function createWorkspace(name: string): Promise<{ workspace_id: string; name: string } | null> {
  try {
    const res = await fetch(`${API_BASE}/workspace/create`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

export async function deleteWorkspace(workspaceId: string): Promise<boolean> {
  try {
    const res = await fetch(`${API_BASE}/workspace/${encodeURIComponent(workspaceId)}`, {
      method: 'DELETE',
      credentials: 'include',
    })
    return res.ok
  } catch {
    return false
  }
}

// ─── ADK Sessions ────────────────────────────────────

export async function listSessions(workspaceId: string): Promise<Session[]> {
  const res = await fetch(
    `${ADK_BASE}/adk_agent/users/${workspaceId}/sessions`,
    { credentials: 'include' }
  )
  if (!res.ok) return []
  return res.json()
}

export async function createSession(workspaceId: string): Promise<Session> {
  const res = await fetch(
    `${ADK_BASE}/adk_agent/users/${workspaceId}/sessions`,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ state: {} }),
    }
  )
  if (!res.ok) throw new Error(`Failed to create session: ${res.status}`)
  return res.json()
}

export async function getSession(workspaceId: string, sessionId: string): Promise<Session | null> {
  const res = await fetch(
    `${ADK_BASE}/adk_agent/users/${workspaceId}/sessions/${sessionId}`,
    { credentials: 'include' }
  )
  if (!res.ok) return null
  return res.json()
}

export async function deleteSession(workspaceId: string, sessionId: string): Promise<boolean> {
  try {
    const res = await fetch(
      `${ADK_BASE}/adk_agent/users/${workspaceId}/sessions/${sessionId}`,
      {
        method: 'DELETE',
        credentials: 'include',
      }
    )
    return res.ok
  } catch {
    return false
  }
}

// ─── Streaming Chat ──────────────────────────────────

const TOOL_DESCRIPTIONS: Record<string, string> = {
  google_list_emails: '📬 Reading Gmail inbox',
  gmail_get_email: '📩 Reading email content',
  gmail_send: '✉️ Sending email',
  gmail_reply: '✉️ Replying to email thread',
  gmail_search_emails: '🔍 Searching Gmail',
  gmail_archive: '📥 Archiving email',
  gmail_mark_as_read: '✉️ Marking email as read',
  google_list_calendar_events: '📅 Fetching Google Calendar events',
  calendar_search_events: '🔍 Searching Google Calendar',
  calendar_create_event: '📅 Creating calendar event',
  calendar_delete_event: '🗑️ Deleting calendar event',
  calendar_update_event: '📅 Updating calendar event',
  calendar_get_event: '📅 Fetching calendar event details',
  github_list_repos: '🐙 Listing GitHub repositories',
  github_list_issues: '🐙 Fetching GitHub issues',
  github_list_pull_requests: '🐙 Fetching GitHub pull requests',
  github_whoami: '👤 Verifying GitHub account',
  github_create_issue: '📝 Creating GitHub issue',
  github_comment_on_issue: '💬 Posting comment on GitHub issue',
  github_close_issue: '🚫 Closing GitHub issue',
  github_create_pr: '🔀 Creating GitHub pull request',
  github_get_issue: '📄 Reading GitHub issue details',
  github_get_pr: '📄 Reading GitHub pull request details',
  github_get_file_contents: '📂 Reading file from GitHub repository',
}

export function formatToolStep(toolName: string): string {
  return TOOL_DESCRIPTIONS[toolName] || `🛠️ Executing tool: ${toolName}`
}

export function runSse(
  workspaceId: string,
  sessionId: string,
  message: string,
  onToken: (token: string) => void,
  onDone: () => void,
  onError: (err: Error) => void,
  onStep?: (stepDescription: string) => void
): AbortController {
  const ctrl = new AbortController()

  const doFetch = (sid: string, isRetry = false) => {
    const body = JSON.stringify({
      app_name: 'adk_agent',
      user_id: workspaceId,
      session_id: sid,
      new_message: { role: 'user', parts: [{ text: message }] },
      streaming: true,
    })

    fetch('/run_sse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      credentials: 'include',
      signal: ctrl.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          if ((res.status === 404 || res.status === 400 || res.status === 500) && !isRetry) {
            try {
              const ns = await createSession(workspaceId)
              doFetch(ns.id, true)
              return
            } catch { /* ignore retry error, fall through */ }
          }
          onError(new Error(`HTTP ${res.status}`))
          return
        }
        if (!res.body) {
          onError(new Error('No response body'))
          return
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                const parts = data?.content?.parts || []

                for (const part of parts) {
                  const fc = part?.functionCall || part?.function_call
                  if (fc?.name && onStep) {
                    onStep(formatToolStep(fc.name))
                  }
                }

                const text = parts?.[0]?.text
                const isFinal = data?.partial === false

                if (text && !isFinal) {
                  onToken(text)
                }
              } catch { /* skip invalid JSON */ }
            }
          }
        }
        onDone()
      })
      .catch((err) => {
        if (err.name !== 'AbortError') onError(err)
      })
  }

  doFetch(sessionId)
  return ctrl
}
