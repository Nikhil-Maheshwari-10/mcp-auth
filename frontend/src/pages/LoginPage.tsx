import React from 'react'
import { getGoogleLoginUrl } from '../lib/api'

interface Props {
  error?: string | null
}

export default function LoginPage({ error }: Props) {
  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon">🤖</div>
          <div>
            <h1>Workspace Agent</h1>
            <span>Powered by Google ADK + MCP</span>
          </div>
        </div>

        <h2 className="login-heading">Sign in to continue</h2>
        <p className="login-sub">
          Access your Gmail, Google Calendar, and GitHub through a single intelligent workspace.
        </p>

        {error && (
          <div style={{
            padding: '10px 14px',
            background: 'rgba(239,68,68,0.1)',
            border: '1px solid rgba(239,68,68,0.25)',
            borderRadius: '8px',
            color: '#fca5a5',
            fontSize: '13px',
            marginBottom: '16px',
          }}>
            {error === 'login_with_google_first'
              ? '⚠️ Please sign in with Google before connecting GitHub.'
              : error === 'session_expired'
              ? '⚠️ Your session expired. Please sign in again.'
              : error === 'invalid_state'
              ? '⚠️ Sign-in session expired or was already completed. Please click below to sign in.'
              : error === 'token_exchange_failed'
              ? '⚠️ Authentication exchange failed. Please sign in again.'
              : `⚠️ ${error}`}
          </div>
        )}

        <a
          href={getGoogleLoginUrl()}
          className="btn btn-google"
          id="google-login-btn"
        >
          <svg width="18" height="18" viewBox="0 0 18 18">
            <path fill="#4285F4" d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z"/>
            <path fill="#34A853" d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.72.48-1.63.77-2.7.77-2.07 0-3.82-1.4-4.45-3.28H1.87v2.07A8 8 0 0 0 8.98 17z"/>
            <path fill="#FBBC05" d="M4.53 10.54A4.87 4.87 0 0 1 4.27 9c0-.53.09-1.05.26-1.54V5.39H1.87A8 8 0 0 0 .98 9c0 1.29.31 2.51.89 3.61l2.66-2.07z"/>
            <path fill="#EA4335" d="M8.98 3.58c1.16 0 2.21.4 3.03 1.18l2.27-2.27A8 8 0 0 0 .98 9l2.85 2.07C4.3 5.07 6.35 3.58 8.98 3.58z"/>
          </svg>
          Continue with Google
        </a>

        <div className="login-divider">
          <span>what you can do</span>
        </div>

        <ul className="login-features">
          <li><span>📧</span> <span>Read, search, compose & reply to Gmail emails</span></li>
          <li><span>📅</span> <span>View, search, create & manage Calendar events</span></li>
          <li><span>🐙</span> <span>Inspect repos, issues & create GitHub pull requests</span></li>
          <li><span>⚡</span> <span>Execute multi-step AI agent workflows in real time</span></li>
        </ul>
      </div>
    </div>
  )
}
