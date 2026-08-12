# 🤖 Personal Workspace Agent: Multi-Account OAuth2 & Workspace MCP AI Engine

**Personal Workspace Agent** is an intelligent, multi-provider AI assistant powered by **Google ADK (Agent Development Kit)** and **FastMCP**. It seamlessly integrates multiple **Gmail**, **Google Calendar**, and **GitHub** accounts within isolated, custom **Workspaces** over OAuth 2.0 with PKCE.

Query across multiple connected email or developer accounts simultaneously in a single prompt, perform write operations with explicit safety confirmations, and switch between isolated workspace environments with zero downtime.

---

## 📽️ System Architecture & Data Flow

```mermaid
graph TD
    User([User]) -->|Interact| UI[React / Vite Frontend]
    UI -->|Session & Auth APIs| API[FastAPI Auth Gateway]
    UI -->|SSE Stream /run_sse| ADK[Google ADK Agent Server]

    subgraph WorkspaceIsolation["Workspace & Multi-Account Isolation"]
        API -->|OAuth 2.0 + PKCE| GoogleOAuth[Google OAuth 2.0]
        API -->|OAuth 2.0| GitHubOAuth[GitHub OAuth 2.0]
        API -->|Read / Write Encrypted Tokens| WorkspaceRepo[Workspace & Token Layer]
        WorkspaceRepo -->|Persist Workspaces & Multi-Tokens| DB[(PostgreSQL Database)]
    end

    subgraph AgentTools["AI Agent & FastMCP Tools"]
        ADK -->|Rotated Key Pool| Model[LLM / AI Model]
        ADK -->|Invoke MCP Tools| Tools{FastMCP Toolset - 25 Tools}
        Tools -->|Ambiguity Guard Check| AmbiguityCheck{check_account_ambiguity}
        AmbiguityCheck -->|Ambiguous| AskUser["Prompt User to Pick Account or All"]
        AmbiguityCheck -->|Resolved| ScopeCheck{Granted Scope Verifier}

        ScopeCheck -->|Granted| ToolExec[Execute Provider REST API]
        ScopeCheck -->|Denied| GuardErr[Return Actionable Scope Guard Error]

        ToolExec -->|Fetch / Send Emails| GmailAPI[Google Gmail API v1]
        ToolExec -->|List / Create Events| CalAPI[Google Calendar API v3]
        ToolExec -->|Repos / Issues / PRs| GitHubAPI[GitHub REST API v3]
    end

    ADK -->|Save Workspace Chat Events| DB
```

---

## ✨ Key Features & Architecture

### 🏢 1. Workspace Isolation & Management Architecture
- **Isolated Workspace Environments**: Workspaces serve as strict isolation boundaries. Each workspace holds its own set of connected OAuth tokens, active accounts, and ADK chat session history.
- **Login Identity vs. Workspace Owner**: Users authenticate via Google OAuth as a primary login identity and can create or switch between multiple Workspaces (e.g. *Personal Workspace*, *Engineering Team*, *Client Projects*).
- **Workspace Operations**:
  - **Inline Workspace Renaming**: Edit and save workspace names in real-time from the Settings UI.
  - **Workspace Switcher**: Dropdown in the sidebar footer to switch environments with 1 click.
  - **Workspace Picker (`/choose-workspace`)**: Dedicated workspace selection screen upon login.
  - **Workspace Reset & Deletion**: Disconnect tokens within a specific workspace or permanently purge a workspace and its chat history without affecting other workspaces.

### 👥 2. Multi-Account OAuth Linking (Gmail, Calendar & GitHub)
- **Multi-Gmail & Multi-Calendar**: Link multiple Google accounts simultaneously within a single workspace (`MAX_LINKED_GMAIL_ACCOUNTS`).
- **Multi-GitHub Integration**: Connect multiple GitHub developer accounts (`@user1`, `@user2`) to inspect repositories across personal and work organizations.
- **Account Profiles & Avatars**: Per-account profile pictures, custom handles, and active account selection (`⭐ Set Active`).
- **Incremental Scope Authorization (`include_granted_scopes`)**: Request additional read/write scopes dynamically without revoking existing tokens.
- **Server-Side Token Encryption**: All access and refresh tokens are encrypted using **Fernet (AES-128)** before database persistence.

### 🤖 3. Intelligent Disambiguation & Labeled Multi-Account Output
- **Dynamic Context Injection**: The agent dynamically receives a live `[CONNECTED ACCOUNTS]` block in its system prompt every turn.
- **Two-Layer Ambiguity Guard**:
  - **Prompt Rule #2**: If 2+ accounts are linked for a provider and the user query is ambiguous, the assistant stops and asks: *"Which account would you like to use? [list accounts]"*.
  - **Tool-Level Interception (`check_account_ambiguity`)**: Tools inspect connected tokens and return a clarification prompt before executing API calls if no account username/email was specified.
- **Parallel Querying ("All" Accounts)**: If the user requests *"check all inboxes"* or *"show PRs from all accounts"*, the agent executes queries across every connected account and groups results under clean Markdown headers (e.g., `### 📧 user@gmail.com`).

### 🛡️ 4. Granular Scope Guards & Confirmation Safety
- **Read vs. Write Scope Isolation**: Differentiates between read operations (e.g., `gmail.readonly`) and mutating operations (e.g., `gmail.send`, `calendar_create_event`, `github_create_pr`).
- **Actionable Scope Guard Errors**: If write scopes were not granted during OAuth login, tools return an actionable error directing the user to click `🔑 Re-authorize` in Settings.
- **Mutating Confirmation Guard**: Prompts for explicit user confirmation before executing any write/delete tool action.

### 🛠️ 5. FastMCP Toolset (25 Active MCP Tools)
- **Gmail Tools (8)**: `google_list_emails`, `gmail_search_emails`, `gmail_get_email`, `gmail_send`, `gmail_reply`, `gmail_archive`, `gmail_mark_as_read`, `google_whoami`.
- **Google Calendar Tools (6)**: `google_list_calendar_events`, `calendar_search_events`, `calendar_get_event`, `calendar_create_event`, `calendar_update_event`, `calendar_delete_event`.
- **GitHub Tools (11)**: `github_list_repos`, `github_list_issues`, `github_list_pull_requests`, `github_get_issue`, `github_get_pr`, `github_get_file_contents`, `github_create_issue`, `github_comment_on_issue`, `github_close_issue`, `github_create_pr`, `github_whoami`.

### 🎨 6. Enhanced Settings UI & System Health Dashboard
- **System Health Diagnostics Bar**: Top status bar displaying real-time operational metrics for `MCP Server`, `PostgreSQL Database`, `Authentication Tokens`, and `Agent Engine`.
- **Scope Badges**: Visual tags (`📖 READ-ONLY` in green vs `⚡ WRITE / MUTATING` in amber) on every tool.
- **Sample Prompt Discovery**: Each tool card features a sample prompt snippet with a 1-click **`📋 Copy`** button for prompt testing.

---

## 🛠️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Frontend** | React 18, Vite, React Router v6, TypeScript, Vanilla CSS |
| **Auth Gateway (Backend)** | FastAPI, httpx, Authlib / OAuth 2.0 PKCE, Cryptography (Fernet) |
| **AI Orchestration** | Google ADK (`google-adk`), LLM Integration |
| **Tool Layer** | FastMCP (Model Context Protocol) |
| **Database** | PostgreSQL 16, SQLAlchemy 2.0 (Async), Asyncpg |
| **Database Migrations** | Alembic |
| **Containerization** | Docker, Docker Compose, Nginx (Alpine), Ngrok |

---

## 🚀 Getting Started

### 1. Prerequisites
- **Docker & Docker Compose** (Recommended)
- **Node.js 20+** (For local frontend dev)
- **Python 3.12+** (For local backend dev)
- **Google Cloud Console OAuth App** (With Gmail & Calendar APIs enabled)
- **GitHub OAuth App**
- **AI Model API Key(s)**

---

### 2. Quickstart with Docker Compose (Recommended)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Nikhil-Maheshwari-10/mcp-auth.git
   cd mcp-auth
   ```

2. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   ```
   Fill in your OAuth credentials and API keys in `.env`.

3. **Launch the Container Stack**:
   ```bash
   docker compose up -d --build
   ```

4. **Access the Application**:
   - Access your application frontend and services via your configured domain or container environment URL.

---

### 3. Environment Variables Reference

| Variable | Description |
| :--- | :--- |
| `POSTGRES_USER` | PostgreSQL superuser username |
| `POSTGRES_PASSWORD` | PostgreSQL superuser password |
| `POSTGRES_DB` | Main database name (`workspace_db`) |
| `DATABASE_URL` | SQLAlchemy async connection string |
| `FERNET_KEY` | 32-byte URL-safe base64 key for token encryption |
| `GOOGLE_CLIENT_ID` | Google OAuth Client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret |
| `GOOGLE_REDIRECT_URI` | Google OAuth Callback URL |
| `MAX_LINKED_GMAIL_ACCOUNTS` | Cap on max connected Gmail accounts per workspace (Default: `3`) |
| `GITHUB_CLIENT_ID` | GitHub OAuth Client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth Client Secret |
| `GITHUB_REDIRECT_URI` | GitHub OAuth Callback URL |
| `NGROK_DOMAIN` | Optional ngrok tunnel domain for public HTTPS callbacks |
| `AI_MODEL_API_KEYS` | Comma-separated API Keys for model orchestration and key rotation |
| `SESSION_SECRET_KEY` | Cryptographic secret for signing session cookies |

---

## 📐 Project Architecture Tree

```text
mcp-auth/
├── adk_agent/              # Google ADK agent definition & key rotation
│   ├── agent.py            # LLM orchestration & context instructions
│   └── prompts.py          # System prompt & multi-account disambiguation rules
├── api/                    # FastAPI Auth Gateway
│   ├── auth/
│   │   ├── google.py       # Google OAuth2 + PKCE + Multi-Account routes
│   │   ├── github.py       # GitHub OAuth2 + Multi-Account routes
│   │   ├── session.py      # Session management with active workspace state
│   │   ├── middleware.py   # Context dependencies (user_id, workspace_id)
│   │   └── refresh.py      # Silent token refresh background logic
│   ├── workspace.py        # Workspace CRUD & switching routes
│   └── main.py             # FastAPI App Entry Point & /me endpoint
├── db/                     # PostgreSQL Database Access Layer
│   ├── engine.py           # Async SQLAlchemy Engine & SessionMaker
│   ├── models.py           # User, Workspace, WorkspaceUser, OAuthToken, Session, AuditLog
│   ├── workspace_repo.py   # Workspace CRUD & sub-based lookup
│   ├── token_repo.py       # Fernet-encrypted token persistence
│   └── audit_repo.py       # Tool execution audit logging
├── frontend/               # React + Vite Frontend App
│   ├── src/
│   │   ├── components/     # WorkspaceSwitcher, Modals, Status Badges
│   │   ├── pages/          # ChatPage, LoginPage, SettingsPage, WorkspacePickerPage
│   │   ├── lib/api.ts      # SSE Stream Client & API Wrappers
│   │   └── index.css       # Vanilla CSS Design Tokens & Glassmorphism
│   ├── Dockerfile          # Multi-stage Nginx Build
│   └── vite.config.ts
├── mcp_server/             # FastMCP Tool Implementations
│   └── tools/
│       ├── common.py       # require_token, check_account_ambiguity, audit logging
│       ├── gmail.py        # 8 Gmail API Tools
│       ├── calendar.py     # 6 Calendar API Tools
│       └── github.py       # 11 GitHub API Tools
├── alembic/                # Database Schema Migrations
├── tests/                  # Multi-account & reauth test suites
│   ├── test_github_multi_account.py
│   ├── test_reauth_flow.py
│   └── workspace_architecture_plan.md
├── docker-compose.yml      # Multi-container Orchestration Setup
└── README.md
```

---

## 🛡️ Security & Data Privacy

- **PKCE OAuth Flow**: Authorization uses Proof Key for Code Exchange (PKCE) to prevent code injection attacks.
- **Fernet Token Encryption**: All access and refresh tokens are encrypted using Fernet symmetric encryption before being saved to PostgreSQL.
- **Server-Side Token Storage**: Tokens are stored server-side and **never** exposed to browser cookies or URL query parameters.
- **Workspace Isolation**: Data, tokens, and conversation histories are strictly scoped to `workspace_id`.
- **HttpOnly Cookies**: Session authentication uses `HttpOnly`, `Secure`, and `SameSite=Lax` cookies.

---

*Developed with ❤️ for Next-Generation Agentic Workspaces.*
