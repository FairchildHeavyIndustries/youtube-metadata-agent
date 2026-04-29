# youtube-metadata-agent

Audits and rewrites YouTube video and channel metadata for B2B clients with underperforming channels. Uses the YouTube Data API v3 for reads and writes, and the Anthropic Batch API to rewrite titles, descriptions, tags, and localizations against a client-supplied SEO brief.

This project was built collaboratively with [Claude Code](https://claude.ai/code). See [CLAUDE.md](CLAUDE.md) for the agent context, architectural conventions, and module reference.



---

## Setup

### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ANTHROPIC_API_KEY, YOUTUBE_CHANNEL_ID
```

### 3. OAuth setup (one-time per client)

The channel owner must complete this step to grant write access:

```bash
python auth/oauth_setup.py
```

This opens a browser, prompts the channel owner to log in, then prints a refresh token. Paste it into `.env` as `GOOGLE_REFRESH_TOKEN`, or save it as a GitHub Actions secret.

---

## Workflow

Each step is a standalone script. No write operations occur before Step 6.

### Step 1 — Fetch
```bash
python agent/fetch.py --client client_name
```
Pulls all video and channel metadata. Writes `clients/client_name/output/current_metadata.json`.

### Step 2 — Backup
```bash
python agent/backup.py --client client_name
```
Creates an immutable `original_backup_<date>.json`. Refuses to overwrite an existing backup.

### Step 3 — Audit
```bash
python agent/audit.py --client client_name
```
Analyzes current metadata and writes `audit_<date>.json` with findings (missing localizations, short descriptions, etc.).

### Step 4 — Rewrite
```bash
python agent/rewrite.py --client client_name
```
Sends each video to Claude with the client SEO brief as the system prompt. Writes `proposed_metadata.json`.

Default: Batch API (`ANTHROPIC_USE_BATCH=true`) — async, results within 24 hours, 50% cheaper.
Real-time: set `ANTHROPIC_USE_BATCH=false` for immediate results via `asyncio`.

### Step 5 — Diff (human review gate)
```bash
python agent/diff.py --client client_name
```
Displays a rich terminal side-by-side diff. Also writes `diff_<date>.md`. **No YouTube writes at this step.** Edit `proposed_metadata.json` manually if needed before approving.

### Step 6 — Push (videos)
```bash
python agent/push.py --client client_name --approve
```
Pushes approved metadata to YouTube. Idempotent (consults `pushed.json` ledger). Use `--resume` to continue an interrupted run. Hard-refuses if `DRY_RUN=true`.

### Step 7 — Channel
```bash
python agent/channel.py --client client_name --approve
```
Updates channel description, keywords, and default language from `clients/client_name/channel.md`.

### Step 8 — Playlists
```bash
python agent/playlists.py --client client_name --approve
```
Creates playlists from `categories.json` and assigns each video to its category.

### Step 9 — Report
```bash
python agent/report.py --client client_name
```
Generates `report_<date>.md` — a before/after summary suitable for client delivery.

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `GOOGLE_CLIENT_ID` | OAuth client ID | required |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | required |
| `GOOGLE_REFRESH_TOKEN` | Populated by `auth/oauth_setup.py` | required |
| `ANTHROPIC_API_KEY` | Anthropic API key | required |
| `YOUTUBE_CHANNEL_ID` | Channel to operate on (e.g. `UCxxxxxxx`) | required |
| `ANTHROPIC_MODEL` | Primary rewrite model | `claude-sonnet-4-6` |
| `ANTHROPIC_ESCALATION_MODEL` | Escalation model for parse failures | `claude-opus-4-7` |
| `ANTHROPIC_VALIDATION_MODEL` | Spot-check validation model | `claude-haiku-4-5-20251001` |
| `ANTHROPIC_USE_BATCH` | Use Batch API (async, 50% cheaper) | `true` |
| `DRY_RUN` | Print-only mode, no YouTube writes | `true` |
| `WRITE_RATE_LIMIT_SECONDS` | Delay between YouTube write calls | `1` |

---

## Adding a New Client

1. Create `clients/{client_name}/brief.md` — SEO rules for Claude (system prompt)
2. Create `clients/{client_name}/categories.json` — playlist structure
3. Create `clients/{client_name}/channel.md` — channel-level metadata YAML
4. Set `YOUTUBE_CHANNEL_ID` in `.env` to the client's channel ID
5. Run `auth/oauth_setup.py` with their Google account
6. Run the full workflow

No code changes required.

---

## Testing

```bash
pytest tests/
```

All tests run with `DRY_RUN=true` and mock external APIs. No live YouTube or Anthropic calls.

---

## Cost Model (50-video channel)

| Scenario | Cost |
|---|---|
| Sonnet 4.6 + Batch API + prompt caching | ~$0.30 |
| Sonnet 4.6 + real-time + prompt caching | ~$0.60 |
| Opus 4.7 escalations (~5 videos) | ~$0.10 additional |
| **Full run, worst case** | **< $1.00** |

## Quota Budget (YouTube Data API v3)

First run for a 50-video channel with 12 playlists uses ~5,653 of the 10,000 daily unit quota. Subsequent read-only runs (fetch, audit) are trivial.

---

## Output Files

All generated files land in `clients/{client}/output/` (gitignored):

| File | Contents |
|---|---|
| `current_metadata.json` | Latest fetch from YouTube |
| `original_backup_<date>.json` | Immutable pre-change archive |
| `proposed_metadata.json` | Claude's rewrites |
| `pushed.json` | Idempotency ledger |
| `audit_<date>.json` | Pre-change findings |
| `diff_<date>.md` | Before/after diff |
| `report_<date>.md` | Client-facing report |
| `escalations.json` | Videos escalated to Opus |
| `parse_errors.json` | Videos Claude could not parse |
| `push_errors.json` | YouTube API write failures |
| `batch_errors.json` | Batch API timeout records |

## License

Licensed under the MIT License — see LICENSE for details.
