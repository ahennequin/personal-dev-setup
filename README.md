# Personal Dev Setup

A self-hosted coding agent orchestrator powered by [Spec-Kit](https://github.github.com/spec-kit/). Listens for GitHub webhooks and automates the full lifecycle of an issue — from spec generation to merged PR — using [OpenCode](https://opencode.ai).

## How it works

1. Create an issue with the `needs-spec` label
2. The bot generates a spec draft via OpenCode and posts it as a comment
3. Review the spec, then add the `spec-approved` label
4. The bot implements the spec, opens a draft PR, and awaits your review
5. Approve or request changes on the PR — the bot will iterate

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (package manager)
- A GitHub personal access token (classic, with `repo` scope)

## Quick start

```bash
# Clone and enter the repo
cd personal-dev-setup

# Install dependencies
uv sync

# Create your env file
cp .env.example .env
```

Edit `.env` with your GitHub credentials (see [Configuration](#configuration) below), then start the server:

```bash
uv run uvicorn api.main:app --port 8080 --reload
```

The server listens for GitHub webhooks at `POST /webhook` (or `/webhook/github-events`).

## Configuration

All settings are read from `.env` via [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

### Essential (required)

| Variable | Description |
|---|---|
| `GITHUB_PAT` | Personal access token with `repo` scope |
| `GITHUB_WEBHOOK_SECRET` | Secret used to verify webhook payloads |
| `GITHUB_USERNAME` | Your GitHub username (used to filter out the bot's own comments when a bot identity is not configured) |
| `GITHUB_REPOS` | Comma-separated list of `owner/repo` to manage (e.g. `~/my-project,my-org/tool`) |

### GitHub App (bot identity, optional)

By default, all API calls use your personal PAT. To make the bot operate as a separate GitHub identity, create a [GitHub App](https://docs.github.com/en/apps/creating-github-apps) and configure these variables:

| Variable | Description |
|---|---|
| `GITHUB_APP_ID` | Numeric App ID (found in your GitHub App settings) |
| `GITHUB_APP_PRIVATE_KEY_PATH` | Full path to the private key `.pem` file downloaded from the app settings |
| `GITHUB_APP_INSTALLATION_ID` | Installation ID — the numeric ID in the URL after installing the app on your repo |
| `GITHUB_BOT_USERNAME` | The bot's username on GitHub (e.g. `speckit-bot[bot]`) |

When all four are set, every API call uses a short-lived installation token obtained by signing a JWT with the app's private key. The token is cached and auto-refreshed.

#### How to create the GitHub App

1. Go to **Settings → Developer settings → GitHub Apps** and click **New GitHub App**
2. Set **GitHub App name** to something descriptive (e.g. `speckit-bot`)
3. Set **Homepage URL** to any valid URL (e.g. `https://github.com`)
4. Disable **Webhook** (this project uses its own webhook with your PAT)
5. Under **Repository permissions**, grant:
   - **Issues**: Read & write
   - **Pull requests**: Read & write
   - **Contents**: Read & write
6. Save, then generate a **private key** (download the `.pem` file)
7. Install the app on your repos at **Install App** in the sidebar
8. After installing, the URL redirects to something like `https://github.com/settings/installations/12345678` — the numeric ID is your installation ID

### OpenCode

| Variable | Default | Description |
|---|---|---|
| `OPENCODE_MODEL` | `opencode/deepseek-v4-flash-free` | Model used by OpenCode for spec and implementation prompts |

### Paths

| Variable | Default | Description |
|---|---|---|
| `REPOS_BASE_PATH` | `~/Code` | Directory where target repos are cloned |
| `SPECKIT_DATA_PATH` | `~/.local/share/speckit` | Directory for state DB and traces DB |

### API

| Variable | Default | Description |
|---|---|---|
| `API_PORT` | `8080` | Port for the uvicorn server |

## GitHub issue labels

The workflow tracks progress through these issue labels:

| Label | Stage |
|---|---|
| `needs-spec` | New issue, waiting for spec generation |
| `spec-draft` | Spec has been generated, awaiting your approval |
| `spec-approved` | Spec is approved, ready for implementation |
| `in-progress` | Implementation in progress, draft PR open |
| `needs-rework` | Changes requested on the PR |
| `done` | PR approved, workflow complete |

Create these labels in your target repos before using the workflow.

Issues should also have a `type:` and `priority:` label (e.g. `type: feature`, `priority: normal`) — these influence the generated spec and implementation.

## Webhook setup

In your GitHub repo settings, add a webhook:

- **Payload URL**: `https://your-server:8080/webhook`
- **Content type**: `application/json`
- **Secret**: The value of `GITHUB_WEBHOOK_SECRET`
- **Events**: Select **Issues**, **Pull request reviews**, and **Issue comments**

## Testing

```bash
uv run pytest
```

All tests use mocks — no real network calls.

## Running locally

```bash
uv run uvicorn api.main:app --port 8080 --reload
```

For local development, use a tool like [ngrok](https://ngrok.com) or [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) to expose your server to GitHub's webhooks.
