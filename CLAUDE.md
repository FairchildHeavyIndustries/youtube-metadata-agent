# YouTube Metadata SEO Agent
### fairchildheavyindustries/youtube-metadata-agent

**Version:** 2.0
**Status:** Step 4 (Rewrite) batch in progress — waiting for poller to retrieve results

**Current run:** Batch `msgbatch_013Ehkp27pVje5sGPJbtdS63` submitted 2026-04-28 ~4:46 PM ET. Batch completed (56/56 succeeded) — poller retrieving results.

**Previous failed run:** Batch `msgbatch_01XUt1HKuu6HQiP6vTd9kGCG` (2026-04-28, ~$9.55) failed due to `max_tokens=2500` truncating responses mid-JSON. Fixed to `max_tokens=6000` in `agent/rewrite.py`.

### How to check for completion

```bash
# Check if proposed_metadata.json has been written (the finish signal):
ls -lh clients/sweepandvac/output/proposed_metadata.json

# Check batch status directly:
python -c "
import anthropic; from dotenv import load_dotenv; load_dotenv()
b = anthropic.Anthropic().messages.batches.retrieve('msgbatch_013Ehkp27pVje5sGPJbtdS63')
print(b.processing_status, b.request_counts)
"

# Watch the polling process:
ps aux | grep rewrite | grep -v grep
```

Once `proposed_metadata.json` exists, run Step 5: `python agent/diff.py --client sweepandvac`

---

## Project Purpose

This agent audits and rewrites YouTube video and channel metadata (titles, descriptions, tags, localizations, playlists, channel keywords, About section) for B2B clients with underperforming channels. The first client is **Sweep & Vac Unlimited** (`@sweepandvac`) — a Puerto Rico-based heavy equipment distributor with 50+ videos averaging 10–50 views on recent uploads.

The agent:
1. Pulls all existing video and channel metadata from the YouTube Data API v3
2. Backs up the original state to an immutable archive before any changes
3. Uses Claude to rewrite titles, descriptions, tags, and localizations against a client-supplied SEO brief
4. Presents a human-reviewable diff before touching anything
5. Pushes approved rewrites back to YouTube via the API, with idempotency and resume support
6. Organizes videos into playlists by product category
7. Updates channel-level metadata (keywords, About section, default language)
8. Outputs a before/after audit report for client delivery

This is a **portfolio-grade agentic workflow** — the pattern generalizes to any client with a YouTube presence. All client-specific logic lives in per-client config files, not code.

---

## Repository Structure

```
youtube-metadata-agent/
├── CLAUDE.md                  ← this file
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
│   └── sweepandvac/
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

---

## Tech Stack

- **Python 3.11+**
- **YouTube Data API v3** — fetch and update video and channel metadata
- **Google OAuth 2.0** — channel owner authorization (one-time, refresh token persisted)
- **Anthropic API** — primary model: **`claude-sonnet-4-6`** with Batch API for rewrites; Opus 4.7 reserved for escalation only (see Cost Model section)
- **`google-api-python-client`** — YouTube API client
- **`google-auth-oauthlib`** — OAuth flow
- **`anthropic`** — Anthropic Python SDK
- **`python-dotenv`** — local env var loading
- **`rich`** — terminal diff display for human review
- **`jinja2`** — report templating
- **`pytest`** — testing
- **`pandoc`** (system CLI, installed via `brew install pandoc`) — converts `diff_<date>.md` to `diff_<date>.docx` for client review. Run: `pandoc clients/{client}/output/diff_<date>.md -o clients/{client}/output/diff_<date>.docx`

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
python agent/fetch.py --client sweepandvac
```
Pulls all video IDs, titles, descriptions, tags, default language, localizations, view counts, and playlist assignments. Also fetches channel-level metadata (description, keywords, branding settings). Writes to `clients/sweepandvac/output/current_metadata.json`.

Uses `videos.list` batched at 50 IDs per call (1 unit per call) and `channels.list` (1 unit).

### Step 2 — Backup
```bash
python agent/backup.py --client sweepandvac
```
Copies `current_metadata.json` to `clients/sweepandvac/output/original_backup_<YYYY-MM-DD>.json`. **Never overwrites an existing backup file** — if one exists for today's date, the script aborts with an error. This file is the restore point if anything goes wrong. It must be created before any push.

### Step 3 — Audit
```bash
python agent/audit.py --client sweepandvac
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
python agent/rewrite.py --client sweepandvac
```
For each video, sends the current metadata to Claude with the client brief (`clients/sweepandvac/brief.md`) as the system prompt. Claude returns rewritten title, description, tags, localizations, and playlist category. Writes to `clients/sweepandvac/output/proposed_metadata.json`.

**Batch mode (default, `ANTHROPIC_USE_BATCH=true`):** submits all videos to the Anthropic Batch API in a single request. Results are returned asynchronously within 24 hours. The script polls every 5 minutes and writes results incrementally as they arrive. When batch mode is enabled, the step is non-blocking — the operator can check back later.

**Real-time mode (`ANTHROPIC_USE_BATCH=false`):** processes videos with `asyncio.gather` in groups of 10 parallel requests for immediate results. Use this when you need the diff the same day.

**Prompt caching:** the brief.md system prompt (~5,500 tokens) is marked for caching with `cache_control: {type: "ephemeral"}`. After the first request, every subsequent call reads the cached brief at 10% of standard input cost. This is the single biggest cost lever — the brief dominates input token count.

**Model escalation:** first pass uses `ANTHROPIC_MODEL` (Sonnet 4.6). Any video that returns a parse error or fails the validation checklist on the second parse attempt is automatically re-submitted using `ANTHROPIC_ESCALATION_MODEL` (Opus 4.7). Escalations are logged to `output/escalations.json` for review.

**Rate limiting:** the rewrite step calls Anthropic, not YouTube. YouTube quota is not consumed here.

### Step 5 — Diff (human review gate)
```bash
python agent/diff.py --client sweepandvac
```
Displays a side-by-side terminal diff of every field for every video using `rich`. Writes a Markdown version to `output/diff_<date>.md` for sharing with the client.

**No changes are made to YouTube at this step.** The operator either approves (proceeds to Step 6) or edits `proposed_metadata.json` manually before approving.

### Step 6 — Push (videos)
```bash
python agent/push.py --client sweepandvac --approve
```
Pushes approved metadata to YouTube via `videos.update`. Behavior:

- **Idempotency:** consults `output/pushed.json` ledger first. Videos already marked as pushed are skipped.
- **Resume:** if interrupted, re-running with `--resume` continues from the last unpushed video.
- **Rate limit:** sleeps `WRITE_RATE_LIMIT_SECONDS` (default 1) between calls.
- **DRY_RUN guard:** if `DRY_RUN=true`, prints what would be sent and refuses to write. This is a hard refusal, not a warning. The flag must be explicitly flipped to `false` for writes to occur.
- **Per-video error isolation:** a failure on video N logs to `output/push_errors.json` and continues to video N+1. Never aborts the run on a single failure.
- **Localizations:** writes `localizations.es` (primary) and `localizations.en` (secondary) per the brief.
- **Default language:** sets `snippet.defaultLanguage` and `snippet.defaultAudioLanguage` to `es` (override per-video if the brief specifies otherwise).

After each successful update, the video ID is appended to `pushed.json` immediately (not at end of run).

### Step 7 — Channel
```bash
python agent/channel.py --client sweepandvac --approve
```
Updates channel-level metadata from `clients/sweepandvac/channel.md`:
- `brandingSettings.channel.description` — Spanish-first About section
- `brandingSettings.channel.keywords` — replacement keyword string
- `brandingSettings.channel.defaultLanguage` — `es`

Same DRY_RUN and approval semantics as Step 6.

### Step 8 — Playlists
```bash
python agent/playlists.py --client sweepandvac --approve
```
Creates playlists from `clients/sweepandvac/categories.json` (checking for existing playlists first by title to avoid duplicates), then assigns each video to its category as determined in the rewrite step.

### Step 9 — Report
```bash
python agent/report.py --client sweepandvac
```
Generates `clients/sweepandvac/output/report_<date>.md` from the audit findings, the diff, and the push ledger. Suitable for direct delivery to the client. Sections:
- Executive summary (videos updated, playlists created, channel changes)
- Audit findings (the "before" picture)
- Sample of rewrites (5 representative videos, before/after)
- Next steps (60- and 90-day review checkpoints)

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
- **Escalation model:** `claude-opus-4-7` (override via `ANTHROPIC_ESCALATION_MODEL` env var) — used only for videos that fail Sonnet's first and second parse attempts
- **Validation model:** `claude-haiku-4-5-20251001` — used for a fast spot-check pass on 10% of completed rewrites to confirm hard rules are followed (title length, tag count, no placeholders)
- **API mode:** Batch API by default (`ANTHROPIC_USE_BATCH=true`); real-time `asyncio` available via flag
- **System prompt:** contents of `clients/{client}/brief.md`, marked with `cache_control: {type: "ephemeral"}` for prompt caching
- **User prompt:** current video metadata as JSON (one video per batch request)
- **Response format:** strict JSON, schema below
- **Max tokens:** 2500 per video
- **Retries:** on parse failure, retry once (real-time) or flag for escalation (batch). Second failure escalates to Opus 4.7. If Opus also fails, log to `parse_errors.json` and skip.

### Cost model

Current API pricing (April 2026):

| Model | Input | Output | Cached input |
|---|---|---|---|
| Haiku 4.5 | $1/M | $5/M | $0.10/M |
| Sonnet 4.6 | $3/M | $15/M | $0.30/M |
| Opus 4.7 | $5/M | $25/M | $0.50/M |

Batch API: **50% off** all token costs. Stacks with caching.

**Estimated cost for 56-video channel rewrite (Sweep & Vac, measured April 2026):**

Per-video token reality: ~19,000 tokens input (brief is not reliably cached in Batch API) + ~6,000 tokens output. The brief.md system prompt is larger than assumed and Batch API caching is less reliable than real-time streaming.

| Scenario | Effective cost |
|---|---|
| Sonnet 4.6, batch, no caching | **~$5–7 total** |
| Sonnet 4.6, real-time, caching warm | **~$2–3 total** |
| Opus 4.7 escalations per video | **~$0.30/video additional** |
| **First run, measured (56 videos, heavy Opus escalation due to truncation bug)** | **~$9.55** |

**Key lesson:** the output schema requires two full 200-word descriptions (ES + EN) plus titles, tags, and notes — actual output is ~4,000–5,000 tokens per video, not 2,000. Use `max_tokens=6000`. With that fix and Sonnet-only (no escalation), expect ~$3–5 for a 50-video channel.

The Pro plan (claude.ai) and the API are billed separately. This agent uses the API exclusively — it has no impact on claude.ai usage limits.

### Required response schema

```json
{
  "title": "string, max 100 chars, follows brief title formula",
  "description": "string, min 200 words, follows brief description structure",
  "tags": ["array", "of", "strings", "min 15 items"],
  "default_language": "es",
  "localizations": {
    "es": { "title": "...", "description": "..." },
    "en": { "title": "...", "description": "..." }
  },
  "playlist_category": "one of the 12 category keys from categories.json",
  "rewrite_notes": "brief explanation of key changes for the diff view"
}
```

The `rewrite_notes` field is for human reviewers in the diff step — not pushed to YouTube.

---

## Error Handling

- **OAuth token expiry:** `token_store.py` handles automatic refresh. If refresh fails, prompt the operator to re-run `auth/oauth_setup.py`.
- **YouTube quota exceeded:** catch `HttpError 403` with reason `quotaExceeded`. Log remaining videos to `output/pending.json` and exit cleanly.
- **YouTube rate limit (429):** exponential backoff up to 3 retries, then log to `push_errors.json` and continue.
- **Claude parse failure (real-time mode):** retry once with an explicit JSON reminder. If it fails twice, escalate to Opus 4.7. If Opus also fails, write raw response to `parse_errors.json` and skip.
- **Claude parse failure (batch mode):** failed batch items are flagged in the batch result. The script automatically re-submits them as a real-time Opus 4.7 call. Logged to `output/escalations.json`.
- **Batch API timeout:** Anthropic Batch API guarantees results within 24 hours. If polling exceeds 26 hours without completion, log the batch ID to `output/batch_errors.json` and exit. The operator can resume by re-running with the stored batch ID.
- **Claude rate limit:** the SDK handles backoff internally for real-time calls. Batch API is not subject to rate limits.
- **Push failure on individual video:** log to `push_errors.json`, continue. Never abort the run.
- **DRY_RUN guard:** if `DRY_RUN=true`, all push/update/insert operations print intended payload and refuse to execute. Tested explicitly in `test_push.py`.
- **Backup missing:** `push.py` and `channel.py` refuse to run if no `original_backup_*.json` exists for the current client. Hard requirement.

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

## Generalizing to New Clients

To onboard a new client:

1. Create `clients/{client_name}/brief.md` with their SEO rules
2. Create `clients/{client_name}/categories.json` with playlist structure
3. Create `clients/{client_name}/channel.md` with channel-level metadata
4. Set `YOUTUBE_CHANNEL_ID` in `.env` to their channel ID
5. Run `auth/oauth_setup.py` with their Google account
6. Run the full workflow

No code changes required. All client-specific logic lives in the three config files.

---

## Out of Scope (v1)

These items are mentioned in the source analysis but deferred:

- **Thumbnails.** Generation and upload of consistent thumbnail templates is a separate workstream — likely a different agent that uses an image generation model. Not in this repo.
- **Cards and end screens.** YouTube's API support for these is limited and clunky; the client's media manager can configure them manually after metadata is in place.
- **Shorts cross-posting.** The vertical/horizontal shoot discipline is a process change, not an automation problem. This agent only handles metadata for content that already exists on the channel.
- **Comment moderation and engagement.** Out of scope.

---

## Deployment Notes

- Designed to run locally for client onboarding, then in GitHub Actions for scheduled monthly refreshes
- Refresh token stored as a GitHub repository secret (`GOOGLE_REFRESH_TOKEN`)
- Output files in `clients/*/output/` are gitignored — they contain client data
- `original_backup_*.json` files should be archived to a separate location (e.g., S3, Google Drive) for long-term retention beyond the active project

---

## Measuring Success

Track these metrics 30/60/90 days after metadata push:

| Metric | Tool | Sweep & Vac baseline |
|---|---|---|
| Views on recent uploads | YouTube Studio Analytics | 10–50/video |
| Impressions from search | YouTube Search report | near zero |
| Click-through rate | YouTube Studio | unknown |
| Channel-level search traffic | YouTube Studio | minimal |
| Organic search ranking | Google Search Console | unlisted |

The Sweep & Vac channel has a 29K-view video from 9 years ago (Cannycom podadoras) that proves the format works on this channel. The goal is to replicate that discoverability across the back catalog.

---

## Contact

**Repo owner:** Fairchild Heavy Industries
**First client:** Sweep & Vac Unlimited, Puerto Rico
**YouTube channel:** `@sweepandvac`
