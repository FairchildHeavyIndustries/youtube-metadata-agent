# YouTube Metadata SEO Agent
### fairchildheavyindustries/youtube-metadata-agent

This file is the agent context and architectural reference for this codebase. It is read by Claude Code at the start of every session. See the README for setup and usage.

---

## Project Purpose

This agent audits and rewrites YouTube video and channel metadata (titles, descriptions, tags, localizations, playlists, channel keywords, About section) for B2B clients with underperforming channels.

The agent:
1. Pulls all existing video and channel metadata from the YouTube Data API v3
2. Backs up the original state to an immutable archive before any changes
3. Uses Claude to rewrite titles, descriptions, tags, and localizations against a client-supplied SEO brief
4. Presents a human-reviewable diff before touching anything
5. Pushes approved rewrites back to YouTube via the API, with idempotency and resume support
6. Organizes videos into playlists by product category
7. Updates channel-level metadata (keywords, About section, default language)
8. Outputs a before/after audit report for client delivery

The pattern generalizes to any client with a YouTube presence. All client-specific logic lives in per-client config files under `clients/` — no code changes required to onboard a new client.

---

## Repository Structure

```
youtube-metadata-agent/
├── CLAUDE.md                  ← this file (agent context + architecture reference)
├── README.md                  ← setup and usage guide
├── pyproject.toml             ← dependencies and project config
├── .env.example               ← env var template (never commit .env)
├── .gitignore
├── auth/
│   ├── oauth_setup.py         ← one-time OAuth 2.0 flow (run by human)
│   └── token_store.py         ← refresh token management with env var fallback
├── agent/
│   ├── fetch.py               ← pull all video + channel metadata
│   ├── backup.py              ← write immutable original_backup_<date>.json
│   ├── rewrite.py             ← Claude rewrites via Anthropic API
│   ├── diff.py                ← terminal diff for human review
│   ├── push.py                ← write video metadata back to YouTube
│   ├── channel.py             ← write channel-level metadata
│   ├── playlists.py           ← create/assign playlists
│   ├── audit.py               ← analyze current state for the report
│   ├── report.py              ← generate before/after report
│   └── ledger.py              ← idempotency tracking (pushed.json)
├── clients/
│   └── example_client/        ← template — copy this for each new client
│       ├── brief.md           ← SEO brief for Claude (system prompt)
│       ├── categories.json    ← playlist categories + assignment hints
│       ├── channel.md         ← channel-level metadata to apply
│       └── output/            ← all generated files (gitignored)
│           ├── original_backup_<date>.json     ← immutable, never overwritten
│           ├── current_metadata.json           ← latest fetch state
│           ├── proposed_metadata.json          ← Claude's rewrites
│           ├── pushed.json                     ← idempotency ledger
│           ├── audit_<date>.json               ← audit findings
│           ├── report_<date>.md                ← client-facing report
│           ├── escalations.json                ← videos escalated to Opus
│           ├── parse_errors.json
│           ├── push_errors.json
│           └── batch_errors.json
├── reports/
│   └── report_template.md     ← jinja2 template for client reports
└── tests/
    ├── test_fetch.py
    ├── test_rewrite.py
    ├── test_push.py           ← always dry-run
    ├── test_ledger.py
    └── fixtures/
        └── sample_video.json
```

Real client folders (e.g. `clients/acme/`) are gitignored — they contain proprietary SEO briefs and channel data. Only `clients/example_client/` is committed as a template.

---

## Tech Stack

- **Python 3.11+**
- **YouTube Data API v3** — fetch and update video and channel metadata
- **Google OAuth 2.0** — channel owner authorization (one-time, refresh token persisted)
- **Anthropic API** — primary model: **`claude-sonnet-4-6`** with Batch API for rewrites; Opus 4.7 reserved for escalation only
- **`google-api-python-client`** — YouTube API client
- **`google-auth-oauthlib`** — OAuth flow
- **`anthropic`** — Anthropic Python SDK
- **`python-dotenv`** — local env var loading
- **`rich`** — terminal diff display for human review
- **`jinja2`** — report templating
- **`pytest`** — testing
- **`pandoc`** (system CLI, `brew install pandoc`) — converts `diff_<date>.md` to `diff_<date>.docx` for client delivery

---

## Environment Variables

Copy `.env.example` to `.env` for local development. In CI (GitHub Actions), populate the same variables as repository secrets.

```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=        # populated by auth/oauth_setup.py
ANTHROPIC_API_KEY=
YOUTUBE_CHANNEL_ID=          # e.g. UCxxxxxxxxxxxxxxx
ANTHROPIC_MODEL=claude-sonnet-4-6          # primary rewrite model
ANTHROPIC_ESCALATION_MODEL=claude-opus-4-7 # used only for validation failures
ANTHROPIC_USE_BATCH=true                   # true = Batch API (async, 50% cheaper); false = real-time
DRY_RUN=true                 # set to false only when ready to push live
WRITE_RATE_LIMIT_SECONDS=1   # delay between YouTube API writes to avoid 429
```

`token_store.py` reads `GOOGLE_REFRESH_TOKEN` from the environment first, then falls back to a local `.tokens.json` file for development. This keeps GitHub Actions and local dev on the same code path.

**Never commit `.env` or `.tokens.json`.** Both are in `.gitignore`.

---

## Authentication — One-Time Setup

YouTube write access requires OAuth 2.0 (not an API key). The channel owner must complete this once:

```bash
python auth/oauth_setup.py
```

This opens a browser window, prompts the channel owner to log in and grant access, then prints the refresh token. Paste it into `.env` (locally) or save it as a GitHub Actions secret. After this step, the agent runs unattended.

**Scopes required:**
- `https://www.googleapis.com/auth/youtube.force-ssl` — read and write video and channel metadata

---

## Agent Workflow

The full workflow is gated by an explicit human-review step. No write operations occur before Step 6.

### Step 1 — Fetch
```bash
python agent/fetch.py --client <client_name>
```
Pulls all video IDs, titles, descriptions, tags, default language, localizations, view counts, and playlist assignments. Also fetches channel-level metadata (description, keywords, branding settings). Writes to `clients/<client_name>/output/current_metadata.json`.

Uses `videos.list` batched at 50 IDs per call (1 quota unit per call) and `channels.list` (1 unit).

### Step 2 — Backup
```bash
python agent/backup.py --client <client_name>
```
Copies `current_metadata.json` to `clients/<client_name>/output/original_backup_<YYYY-MM-DD>.json`. **Never overwrites an existing backup file** — if one exists for today's date, the script aborts. This file is the restore point if anything goes wrong. It must exist before any push step will run.

### Step 3 — Audit
```bash
python agent/audit.py --client <client_name>
```
Analyzes `current_metadata.json` and writes `output/audit_<date>.json` with findings:
- Count of videos with English-only titles
- Count of videos with descriptions under 100 words
- Count of videos with fewer than 5 tags
- Count of videos missing location tags
- Count of videos with no playlist assignment
- Channel-level findings (keywords, About section, default language)

These findings populate the "Before" half of the client report.

### Step 4 — Rewrite
```bash
python agent/rewrite.py --client <client_name>
```
For each video, sends the current metadata to Claude with the client brief (`clients/<client_name>/brief.md`) as the system prompt. Claude returns rewritten title, description, tags, localizations, and playlist category. Writes to `clients/<client_name>/output/proposed_metadata.json`.

**Batch mode (default, `ANTHROPIC_USE_BATCH=true`):** submits all videos to the Anthropic Batch API in a single request. Results are returned asynchronously within 24 hours. The script polls every 5 minutes and writes results incrementally as they arrive.

**Real-time mode (`ANTHROPIC_USE_BATCH=false`):** processes videos with `asyncio.gather` in groups of 10 parallel requests for immediate results.

**Prompt caching:** the brief.md system prompt is marked for caching with `cache_control: {type: "ephemeral"}`. After the first request, every subsequent call reads the cached brief at 10% of standard input cost. This is the single biggest cost lever — the brief dominates input token count.

**Model escalation:** first pass uses `ANTHROPIC_MODEL` (Sonnet 4.6). Any video that returns a parse error or fails validation on the second attempt is automatically re-submitted using `ANTHROPIC_ESCALATION_MODEL` (Opus 4.7). Escalations are logged to `output/escalations.json`.

**Important:** the output schema requires two full 200-word descriptions (primary language + English) plus titles, tags, and notes — actual output runs ~4,000–5,000 tokens per video. Use `max_tokens=6000` or responses will be truncated mid-JSON.

### Step 5 — Diff (human review gate)
```bash
python agent/diff.py --client <client_name>
```
Displays a side-by-side terminal diff of every field for every video using `rich`. Writes a Markdown version to `output/diff_<date>.md` for sharing with the client.

**No changes are made to YouTube at this step.** Edit `proposed_metadata.json` manually if needed before approving.

### Step 6 — Push (videos)
```bash
python agent/push.py --client <client_name> --approve
```
Pushes approved metadata to YouTube via `videos.update`. Key behaviors:

- **Idempotency:** consults `output/pushed.json` ledger first. Videos already marked as pushed are skipped.
- **Resume:** if interrupted, re-running with `--resume` continues from the last unpushed video.
- **DRY_RUN guard:** if `DRY_RUN=true`, prints what would be sent and refuses to write. Hard refusal, not a warning. Must be explicitly set to `false`.
- **Per-video error isolation:** a failure on video N logs to `push_errors.json` and continues to N+1.
- **Ledger writes:** each successful push appends to `pushed.json` immediately, not at end of run.

### Step 7 — Channel
```bash
python agent/channel.py --client <client_name> --approve
```
Updates channel-level metadata from `clients/<client_name>/channel.md`:
- `brandingSettings.channel.description`
- `brandingSettings.channel.keywords`
- `brandingSettings.channel.defaultLanguage`

Same DRY_RUN and approval semantics as Step 6.

### Step 8 — Playlists
```bash
python agent/playlists.py --client <client_name> --approve
```
Creates playlists from `categories.json` (checking for existing playlists first by title to avoid duplicates), then assigns each video to its category as determined in the rewrite step.

### Step 9 — Report
```bash
python agent/report.py --client <client_name>
```
Generates `clients/<client_name>/output/report_<date>.md` from the audit findings, the diff, and the push ledger. Suitable for direct delivery to the client.

---

## Quota Budget

YouTube Data API v3 quota: **10,000 units/day**.

| Operation | Cost/call | Calls (50 videos, 12 playlists) | Subtotal |
|---|---|---|---|
| `videos.list` (batched 50) | 1 | 1 | 1 |
| `channels.list` | 1 | 1 | 1 |
| `playlists.list` | 1 | 1 | 1 |
| `videos.update` | 50 | 50 | 2,500 |
| `channels.update` | 50 | 1 | 50 |
| `playlists.insert` | 50 | 12 | 600 |
| `playlistItems.insert` | 50 | 50 | 2,500 |
| **Total first run** | | | **~5,653** |

Comfortably under the daily quota. Subsequent runs (re-fetches, audits) are read-only and trivial.

If quota is exceeded mid-run, the agent catches `HttpError 403` with reason `quotaExceeded`, writes the unprocessed video IDs to `output/pending.json`, and exits cleanly. Resume the next day with `--resume`.

---

## Rewrite Module — Claude Integration

`agent/rewrite.py` calls the Anthropic API using the Batch API by default.

- **Primary model:** `claude-sonnet-4-6` (override via `ANTHROPIC_MODEL` env var)
- **Escalation model:** `claude-opus-4-7` (override via `ANTHROPIC_ESCALATION_MODEL`) — used only for videos that fail Sonnet's first and second parse attempts
- **Validation model:** `claude-haiku-4-5-20251001` — fast spot-check pass on 10% of completed rewrites to confirm hard rules are followed (title length, tag count, no placeholders)
- **Hard validation rules (enforced in `_validate`):** primary title ≤100 chars, **every localization title ≤100 chars** (YouTube rejects with 400 `invalidVideoMetadata` if any localization title exceeds 100), description ≥200 words, tags ≥15, `playlist_category` must be in `categories.json`
- **API mode:** Batch API by default; real-time `asyncio` available via `ANTHROPIC_USE_BATCH=false`
- **System prompt:** contents of `clients/{client}/brief.md`, marked with `cache_control: {type: "ephemeral"}` for prompt caching
- **User prompt:** current video metadata as JSON (one video per batch request)
- **Response format:** strict JSON (schema below)
- **Max tokens:** 6000 per video
- **Retries:** on parse failure, retry once (real-time) or flag for escalation (batch). Second failure escalates to Opus 4.7. If Opus also fails, log to `parse_errors.json` and skip.

### Cost model

Current API pricing:

| Model | Input | Output | Cached input |
|---|---|---|---|
| Haiku 4.5 | $1/M | $5/M | $0.10/M |
| Sonnet 4.6 | $3/M | $15/M | $0.30/M |
| Opus 4.7 | $5/M | $25/M | $0.50/M |

Batch API: **50% off** all token costs. Stacks with caching.

Estimated cost for a 50-video channel rewrite:

| Scenario | Effective cost |
|---|---|
| Sonnet 4.6, batch, no caching | ~$5–7 total |
| Sonnet 4.6, real-time, caching warm | ~$2–3 total |
| Opus 4.7 escalations | ~$0.30/video additional |

Note: prompt caching is less reliable in Batch API mode than real-time — brief.md may not be cached across batch requests. Real-time mode with warm cache is the most cost-efficient path for channels with large briefs.

### Required response schema

```json
{
  "title": "string, max 100 chars",
  "description": "string, min 200 words",
  "tags": ["array of strings, min 15 items"],
  "default_language": "es",
  "localizations": {
    "es": { "title": "...", "description": "..." },
    "en": { "title": "...", "description": "..." }
  },
  "playlist_category": "one of the category keys from categories.json",
  "rewrite_notes": "brief explanation of key changes for the diff view"
}
```

`rewrite_notes` is for human reviewers in the diff step — not pushed to YouTube.

---

## Error Handling

- **OAuth token expiry:** `token_store.py` handles automatic refresh. If refresh fails, re-run `auth/oauth_setup.py`.
- **YouTube quota exceeded:** catch `HttpError 403 quotaExceeded`. Log remaining videos to `output/pending.json` and exit cleanly.
- **YouTube rate limit (429):** exponential backoff up to 3 retries, then log to `push_errors.json` and continue.
- **Claude parse failure (real-time):** retry once with an explicit JSON reminder. Second failure escalates to Opus 4.7. If Opus also fails, write raw response to `parse_errors.json` and skip.
- **Claude parse failure (batch):** failed batch items are automatically re-submitted as a real-time Opus 4.7 call. Logged to `output/escalations.json`.
- **Batch API timeout:** Anthropic guarantees results within 24 hours. If polling exceeds 26 hours, log the batch ID to `output/batch_errors.json` and exit for manual resume.
- **Push failure on individual video:** log to `push_errors.json`, continue. Never abort the run.
- **DRY_RUN guard:** if `DRY_RUN=true`, all push/update/insert operations print intended payload and refuse to execute. Tested explicitly in `test_push.py`.
- **Backup missing:** `push.py` and `channel.py` refuse to run if no `original_backup_*.json` exists for the current client.

---

## Testing

```bash
pytest tests/
```

- `test_fetch.py` — mocks YouTube API responses, validates output JSON schema
- `test_rewrite.py` — mocks Anthropic API, validates output JSON has all required keys, title under 100 chars, description over 200 words, 15+ tags
- `test_push.py` — always runs in dry-run mode, validates API call payload structure
- `test_ledger.py` — validates idempotency ledger correctly skips already-pushed videos and supports resume

Coverage target: 80%+ on `agent/` modules.

---

## Adding a New Client

1. Copy `clients/example_client/` to `clients/{client_name}/`
2. Edit `brief.md` with the client's SEO rules, tone, and hard constraints
3. Edit `categories.json` with their playlist structure
4. Edit `channel.md` with their channel-level metadata
5. Set `YOUTUBE_CHANNEL_ID` in `.env` to their channel ID
6. Run `auth/oauth_setup.py` with their Google account
7. Run the full workflow

No code changes required.

---

## Out of Scope (v1)

- **Thumbnails.** Consistent thumbnail generation is a separate workstream, likely a different agent using an image generation model.
- **Cards and end screens.** YouTube's API support is limited; configure manually after metadata is in place.
- **Shorts cross-posting.** This agent only handles metadata for content that already exists on the channel.
- **Comment moderation and engagement.** Out of scope.

---

## Deployment Notes

- Designed to run locally for client onboarding, then in GitHub Actions for scheduled monthly refreshes
- Refresh token stored as a GitHub repository secret (`GOOGLE_REFRESH_TOKEN`)
- Output files in `clients/*/output/` are gitignored — they contain client data
- `original_backup_*.json` files should be archived externally (e.g., S3, Google Drive) for long-term retention

---

## Measuring Success

Track these metrics 30/60/90 days after metadata push:

| Metric | Tool |
|---|---|
| Views on recent uploads | YouTube Studio Analytics |
| Impressions from search | YouTube Search report |
| Click-through rate | YouTube Studio |
| Channel-level search traffic | YouTube Studio |
| Organic search ranking | Google Search Console |
