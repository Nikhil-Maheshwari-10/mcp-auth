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
          {/* Gmail — official multicolor M icon */}
          <li>
            <span className="feat-icon">
              <svg width="22" height="22" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                <path fill="#4caf50" d="M45 16.2l-5 2.75-5 4.75V40h7c1.657 0 3-1.343 3-3V16.2z"/>
                <path fill="#1e88e5" d="M3 16.2l3.819 2.495L13 23.7V40H6c-1.657 0-3-1.343-3-3V16.2z"/>
                <polygon fill="#e53935" points="35,11.2 24,19.45 13,11.2 12,17 13,23.7 24,31.95 35,23.7 36,17"/>
                <path fill="#c62828" d="M3,12.298V16.2l10,7.5V11.2L9.876,8.859C9.132,8.301,8.228,8,7.298,8h0C4.924,8,3,9.924,3,12.298z"/>
                <path fill="#fbc02d" d="M45,12.298V16.2l-10,7.5V11.2l3.124-2.341C38.868,8.301,39.772,8,40.702,8h0C43.076,8,45,9.924,45,12.298z"/>
              </svg>
            </span>
            <span>Read, search, compose &amp; reply to Gmail emails</span>
          </li>

          {/* Google Calendar — official blue-header calendar with 31 */}
          <li>
            <span className="feat-icon">
              <svg width="22" height="22" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
                <rect x="5" y="8" width="38" height="34" rx="3" fill="white"/>
                <rect x="5" y="8" width="38" height="11" rx="0" fill="#1565c0"/>
                <rect x="5" y="14" width="38" height="5" fill="#1565c0"/>
                <rect x="8" y="3" width="5" height="10" rx="2.5" fill="#1565c0"/>
                <rect x="35" y="3" width="5" height="10" rx="2.5" fill="#1565c0"/>
                <text x="24" y="36" fontFamily="'Google Sans',Arial,sans-serif" fontSize="14" fontWeight="700" textAnchor="middle" fill="#1565c0">31</text>
                <rect x="11" y="26" width="4" height="4" rx="1" fill="#e53935"/>
                <rect x="22" y="26" width="4" height="4" rx="1" fill="#f57f17"/>
                <rect x="33" y="26" width="4" height="4" rx="1" fill="#33691e"/>
              </svg>
            </span>
            <span>View, search, create &amp; manage Calendar events</span>
          </li>

          {/* GitHub */}
          <li>
            <span className="feat-icon">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="#e6edf3">
                <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z"/>
              </svg>
            </span>
            <span>Inspect repos, issues &amp; create GitHub pull requests</span>
          </li>

          {/* Agent */}
          <li>
            <span className="feat-icon" style={{ fontSize: 18 }}>⚡</span>
            <span>Execute multi-step AI agent workflows in real time</span>
          </li>
        </ul>
      </div>
    </div>
  )
}
