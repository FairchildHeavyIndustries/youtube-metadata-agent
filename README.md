# youtube-metadata-agent

Audits and rewrites YouTube video and channel metadata for B2B clients with underperforming channels. Uses the YouTube Data API v3 for reads and writes, and the Anthropic Batch API to rewrite titles, descriptions, tags, and localizations against a client-supplied SEO brief.

Built collaboratively with [Claude Code](https://claude.ai/code). See [CLAUDE.md](CLAUDE.md) for architectural conventions and module reference.

---

## What it does

For one client channel, in order:

1. **Fetch** every video and the channel itself from the YouTube Data API
2. **Backup** the original state to an immutable archive (a hard prerequisite for every later step)
3. **Audit** the current metadata — counts of missing localizations, short descriptions, sparse tags, etc.
4. **Rewrite** titles, descriptions, tags, and Spanish/English localizations through Claude, guided by a client-specific SEO brief
5. **Diff** before/after side-by-side in the terminal — the human approval gate
6. **Push** the rewrites back to YouTube, idempotently (per-video ledger; safe to resume any time)
7. **Channel** — update channel description, keywords, and default language
8. **Playlists** — create category playlists from a config file and assign every video
9. **Report** — produce a client-facing before/after Markdown report

All client-specific data lives in `clients/<client_name>/`. Onboarding a new client is config-only — no code changes.

---

## Setup

### 1. Install dependencies

```bash
pip install -e ".[dev]"
```

Python 3.11+. `pandoc` is also useful for converting the diff to `.docx` for client delivery (`brew install pandoc`).

### 2. Create a Google Cloud OAuth client

The agent writes to YouTube via OAuth 2.0 (an API key is not enough for write scopes).

1. Open https://console.cloud.google.com/, create a new project
2. **APIs & Services → Library** → enable **YouTube Data API v3**
3. **APIs & Services → Credentials** → **Create Credentials → OAuth client ID**
   - Application type: **Desktop app**
4. Note the **Client ID** and **Client secret**
5. **APIs & Services → OAuth consent screen** → User type **External**
6. **Audience → Test users → + Add users** → add the Google account that will run `oauth_setup.py`. Without this, that account hits `Error 403: access_denied` at consent. (See [OAuth notes](#oauth-notes) for why this matters.)

### 3. Configure environment

```bash
cp .env.example .env
# Fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, ANTHROPIC_API_KEY, YOUTUBE_CHANNEL_ID
```

### 4. Run OAuth setup (per client)

```bash
python auth/oauth_setup.py
```

A browser opens, the user signs in, the script prints a refresh token and writes it to `.tokens.json`. Copy the token into `.env` as `GOOGLE_REFRESH_TOKEN`.

### 5. Verify OAuth identity (recommended before any write)

The token must be acting-as the channel you intend to modify. Run:

```bash
python -c "from agent.fetch import get_youtube_client; from dotenv import load_dotenv; load_dotenv(); import os; r = get_youtube_client().channels().list(part='snippet', mine=True).execute(); item = r['items'][0]; print('Token acts-as:', item['id'], item['snippet']['title']); print('Target:      ', os.environ['YOUTUBE_CHANNEL_ID']); print('MATCH' if item['id'] == os.environ['YOUTUBE_CHANNEL_ID'] else 'MISMATCH — re-run oauth_setup.py')"
```

If `MISMATCH`, do not run any write step. See [OAuth notes](#oauth-notes).

---

## Workflow

Each step is a standalone, idempotent script. **No write operations occur before Step 6.** All writes default to dry-run; pass `DRY_RUN=false` inline to push live.

### Step 1 — Fetch
```bash
python agent/fetch.py --client <client>
```
Pulls all video and channel metadata. Writes `clients/<client>/output/current_metadata.json`.

**Look for:** the JSON should contain every video on the channel. Spot-check the count against YouTube Studio.

### Step 2 — Backup
```bash
python agent/backup.py --client <client>
```
Creates an immutable `original_backup_<date>.json`. Refuses to overwrite an existing backup for the same date.

**Look for:** the backup file appears in `clients/<client>/output/`. This is the restore point — `push.py` and `channel.py` refuse to run without it.

### Step 3 — Audit
```bash
python agent/audit.py --client <client>
```
Analyzes current metadata and writes `audit_<date>.json` (counts of English-only titles, short descriptions, sparse tags, etc.). Feeds the "Before" half of the final report.

### Step 4 — Rewrite
```bash
python agent/rewrite.py --client <client>
```
Sends each video to Claude with the client SEO brief as the cached system prompt. Writes `proposed_metadata.json`.

- **Default:** Batch API (`ANTHROPIC_USE_BATCH=true`) — async, results within 24 hours, 50% cheaper.
- **Real-time:** `ANTHROPIC_USE_BATCH=false` for immediate results via `asyncio`.
- **Escalation:** parse failures auto-retry on the escalation model (default: current frontier model — see env vars), logged to `escalations.json`.

**Look for:** every video has rewritten `title`, `description`, `tags` (15+), `localizations.es`, `localizations.en`, and a `playlist_category` matching one of the keys in `categories.json`.

### Step 5 — Diff (human review gate)
```bash
python agent/diff.py --client <client>
```
Renders a `rich` side-by-side diff in the terminal. Also writes `diff_<date>.md` for sharing with the client.

**No YouTube writes at this step.** Edit `proposed_metadata.json` manually if anything needs adjustment before approving.

### Step 6 — Push videos
```bash
DRY_RUN=false python -m agent.push --client <client> --approve
```
Pushes approved metadata to YouTube via `videos.update`. Idempotent (consults `pushed.json`); safe to re-run. Per-video errors land in `push_errors.json`; the run continues.

**Look for:** `pushed.json` grows by one entry per success. Spot-check a couple of videos in YouTube Studio — title, description, tags, default language, and Spanish/English localizations should all be live.

### Step 7 — Channel
```bash
DRY_RUN=false python -m agent.channel --client <client> --approve
```
Updates channel description, keywords, and default language from `clients/<client>/channel.md`.

**Look for:** YouTube Studio → Customisation → Basic info reflects the new description and keywords. Channel description is hard-capped at 1000 characters; the script truncates and warns.

### Step 8a — Cleanup legacy playlists (optional)
```bash
DRY_RUN=false python -m agent.playlists_cleanup --client <client> --approve
```
For channels with pre-existing playlists not in `categories.json`. Empties each (videos themselves are untouched) and sets privacy to Private. Writes `legacy_playlists_<date>.json`.

**Why empty + private rather than delete:** Channel Editors cannot delete playlists; only the channel Owner can. Empty + private removes them from public surfaces; the Owner deletes them in Studio later. The cleanup file is picked up by `report.py` to render a "Manual Deletion Required" section.

### Step 8b — Create playlists + assign videos
```bash
DRY_RUN=false python -m agent.playlists --client <client> --approve
```
Creates one playlist per category in `categories.json`, then assigns every video to its category.

- Two ledgers: `created_playlists.json` and `playlist_assignments.json`. Both append after every successful write — re-running is always safe.
- Reconciles against the live channel before creating, so a partial prior run doesn't produce duplicates.
- Aborts cleanly on `403 quotaExceeded` (failed writes still cost quota — see [quota budget](#quota-budget)).

**Look for:** the channel's Playlists tab on YouTube shows one playlist per non-empty category. Click into one and confirm the expected videos are present. Empty categories will not appear publicly — that's YouTube's behavior, not a bug.

### Step 9 — Report
```bash
python agent/report.py --client <client>
```
Generates `report_<date>.md` — before/after summary suitable for client delivery. Includes audit findings, rewrite stats, push ledger, playlist summary, and any manual-action items.

---

## OAuth notes

**Test-mode tokens expire every 7 days.** OAuth clients in "Testing" status (the default until Google verification) auto-revoke their refresh tokens weekly. When `invalid_grant` errors appear, re-run `auth/oauth_setup.py`. Verifying the app would remove this limit but requires Google's review process for sensitive scopes — generally not worth it for an internal agent.

**OAuth identity vs target channel.** `videos.update` and `channels.update` route by resource ID, so they always hit the right channel. **`playlists.insert` does not** — it always creates the playlist under whichever channel the OAuth token is currently acting-as. The `YOUTUBE_CHANNEL_ID` env var has no effect on this routing.

This matters when the OAuth user is a Channel Editor on the target channel but also owns a different channel of their own: OAuth defaults to the owned channel, and playlist creation lands on the wrong place. The verify step in [setup](#5-verify-oauth-identity-recommended-before-any-write) catches this in 1 quota unit before any writes happen.

**To get a correctly-bound token, use any of:**
- The channel **Owner**'s Google account (cleanest — no ambiguity)
- A Workspace (custom-domain) account that has Editor access on the target channel and no YouTube channels of its own
- A vanilla Google account that's an Editor and has not created any channel of its own (Google sometimes forces channel creation before letting you accept Editor invites — verify the verify step before pushing)

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `GOOGLE_CLIENT_ID` | OAuth client ID | required |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret | required |
| `GOOGLE_REFRESH_TOKEN` | Populated by `auth/oauth_setup.py` | required |
| `ANTHROPIC_API_KEY` | Anthropic API key | required |
| `YOUTUBE_CHANNEL_ID` | Channel to operate on (e.g. `UCxxxxxxx`) | required |
| `ANTHROPIC_MODEL` | Primary rewrite model — pick a current mid-tier Claude (balanced cost/quality) | see `.env.example` |
| `ANTHROPIC_ESCALATION_MODEL` | Escalation model for parse failures — pick the current frontier Claude | see `.env.example` |
| `ANTHROPIC_VALIDATION_MODEL` | Spot-check validation model — pick the current fast/cheap Claude | see `.env.example` |
| `ANTHROPIC_USE_BATCH` | Use Batch API (async, 50% cheaper) | `true` |
| `DRY_RUN` | Print-only mode, no YouTube writes | `true` |
| `WRITE_RATE_LIMIT_SECONDS` | Delay between YouTube write calls | `1` |
| `PLAYLIST_CREATE_DELAY_SECONDS` | Delay between `playlists.insert` calls | `10` |

Set `DRY_RUN=false` inline at the command line rather than editing `.env` — keeps `.env` defaulted to safe.

---

## Adding a new client

1. Copy `clients/example_client/` to `clients/<client>/`
2. Edit `brief.md` — SEO rules, tone, hard constraints (used as Claude's cached system prompt)
3. Edit `categories.json` — playlist structure with `key`, `title_es`, `description`, and assignment hints
4. Edit `channel.md` — channel description, keywords, default language
5. Set `YOUTUBE_CHANNEL_ID` in `.env`
6. Add the client account to your Cloud project's OAuth Test users list
7. Run `auth/oauth_setup.py` and verify identity (see Setup → Step 5)
8. Run the workflow

No code changes required.

---

## Testing

```bash
pytest tests/
```

All tests run with `DRY_RUN=true` and mock external APIs. No live YouTube or Anthropic calls. Coverage target: 80%+ on `agent/` modules.

---

## Cost model (50-video channel)

| Scenario | Cost |
|---|---|
| Mid-tier model + Batch API + prompt caching | ~$0.30 |
| Mid-tier model + real-time + prompt caching | ~$0.60 |
| Frontier-model escalations (~5 videos) | ~$0.10 additional |
| **Full run, worst case** | **< $1.00** |

Figures based on Claude pricing at the time of writing; recompute with current rates if budgets matter.

## Quota Budget

YouTube Data API v3: **10,000 units/day**. A first-run for a 50-video channel with 13 playlists costs ~5,650 units. Subsequent fetches and audits are read-only and trivial.

**Failed writes still cost quota.** A `playlists.insert` or `playlistItems.insert` that returns 429 or any other error still consumes 50 units. `playlists.py` aborts on first `403 quotaExceeded` rather than retrying — every retry deepens the hole. Quota resets at midnight Pacific; the ledgers make every step idempotent on resume.

---

## Output files

All generated files land in `clients/<client>/output/` (gitignored):

| File | Contents |
|---|---|
| `current_metadata.json` | Latest fetch from YouTube |
| `original_backup_<date>.json` | Immutable pre-change archive |
| `proposed_metadata.json` | Claude's rewrites |
| `pushed.json` | Idempotency ledger for `videos.update` |
| `created_playlists.json` | Idempotency ledger for `playlists.insert` |
| `playlist_assignments.json` | Idempotency ledger for `playlistItems.insert` |
| `legacy_playlists_<date>.json` | Cleanup summary (Step 8a) |
| `audit_<date>.json` | Pre-change findings |
| `diff_<date>.md` | Before/after diff |
| `report_<date>.md` | Client-facing report |
| `escalations.json` | Videos escalated to Opus |
| `parse_errors.json` | Videos Claude could not parse |
| `push_errors.json` | YouTube API write failures |
| `batch_errors.json` | Batch API timeout records |

---

## License

MIT — see LICENSE.
