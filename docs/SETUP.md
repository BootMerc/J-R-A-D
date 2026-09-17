# Setup & Usage Reference

> This is the detailed setup/usage reference. For the project overview,
> architecture, and screenshots, see the [main README](../README.md).

# Recruitment Automation Dashboard

A locally-hosted dashboard for distributing recruitment posts across Facebook
groups, Telegram channels, and TikTok — built to eliminate the repetitive
parts of posting 50-100 job ads a day, without bypassing any platform's
restrictions.

**Cost: $0.** Everything runs on your own Windows PC. No cloud hosting, no
paid databases, no paid automation platforms. Verified feature by feature:

| Feature | Cost | Why |
|---|---|---|
| Jobs, Destinations, Templates, Post Creator | $0 | Local SQLite + FastAPI + Streamlit — no cloud service of any kind |
| Queue, Scheduler, Calendar | $0 | Same local database and local Python process; the scheduler is a background thread, not an external cron/cloud job |
| Facebook Assistant | $0 | Uses your own already-logged-in browser session — no Facebook API, no ad spend |
| Telegram | $0 | The Bot API is free with no paid tier, subject only to Telegram's own fair-use rate limits |
| TikTok (default, manual) | $0 | Local image generation (Pillow) + posting from your own phone/account |
| TikTok (optional Content Posting API) | Not built | Gated behind TikTok's own app-audit approval, not a fee — see `PROJECT_STATUS.md` for why this path was deliberately left unbuilt |
| Analytics | $0 | Manually-entered numbers, stored locally — nothing calls a paid analytics API |
| Backup/restore | $0 | Plain local file copies |
| AI-assisted content (optional, never built) | Pay-per-use if you configure it | The only place a real ongoing cost could enter — entirely opt-in via your own `AI_API_KEY`, not required for any feature above |

**Status:** Phase 14 of 14 (Final polish) complete — all 14 phases done.
See `PROJECT_STATUS.md` for the authoritative, up-to-date state of the
project — that file is what a new Claude session (or you, months from
now) should read first.

---

## What this is (and isn't)

- ✅ Automates what platforms actually let you automate: Telegram posting,
  via the official Bot API.
- ✅ Assists with what platforms don't: Facebook groups get a **manual,
  browser-assisted** workflow — the app opens the group and copies your post
  to the clipboard; you click Post yourself. Nothing automates clicks on
  Facebook's own site.
- ✅ TikTok: manual caption + visual generation by default. The official
  Content Posting API was deliberately **not** built — it needs both real
  app-audit approval from TikTok and an OAuth token-storage schema this
  project doesn't have yet (see `PROJECT_STATUS.md`) — so
  `TIKTOK_CLIENT_KEY`/`TIKTOK_CLIENT_SECRET` exist as placeholder settings
  only; setting them doesn't unlock anything today.
- ❌ No CAPTCHA solving, no stealth automation, no bypassing rate limits or
  authentication. If a platform doesn't support something, the app tells you
  so and gives you a manual path instead of faking it.

## Features available now (all 14 phases complete)

- FastAPI backend with a health check endpoint (`/health`) and interactive
  API docs (`/docs`)
- Full database schema (six tables — see the ERD below) via SQLAlchemy 2.0,
  running on local SQLite
- Environment-based configuration (`.env`), never hard-coded secrets
- Rotating file + console logging
- **Jobs**: create, edit, search, filter by status, duplicate, close,
  archive/unarchive
- **Destinations**: create, edit, delete, activate/deactivate, tags
  (many-to-many), search, filter by platform/category/location/language/tag,
  CSV import (row-by-row error reporting) and export
- **Post Templates**: create, edit, delete, activate/deactivate,
  `{{variable}}` rendering against a real job with a live preview,
  automatic detection of typo'd/unrecognized variables, platform-specific
  formatting, Arabic/English/bilingual language field. 7 starter templates
  are seeded automatically on first run — fully editable, never re-seeded
  once you have templates of your own
- **Post Creator**: generate posts from a job + one or more destinations
  (template auto-selected per platform, or force one specific template);
  generate **variations** — several tones for the same job/destination
  side by side; edit generated content by hand; copy with one click;
  delete with confirmation
- **Queue**: batch queue creation across many destinations at once with a
  staggered posting window (Section 31's 50 Facebook + 10 Telegram + 1
  TikTok pattern); promote individual Draft posts into the queue; Start /
  Pause / Resume / Skip / Retry actions with clear state-transition
  validation (e.g. can't retry a post that isn't Failed); a progress
  summary by status; internal spam-protection warnings (inactive
  destination, cooldown not met, daily limit reached, already-queued
  duplicate) that inform without blocking — these are workflow safeguards,
  not platform-restriction bypasses
- **Facebook Assistant**: works through your Queued Facebook posts one
  group at a time — opens the destination in your browser and copies the
  post to your clipboard automatically, you paste and click Post yourself,
  then mark what happened (Posted/Skip/Failed/Pause/Next) and move on.
  Keyboard shortcuts (Enter/S/P/N) for the common actions. Nothing here
  ever automates a click on Facebook's own page — see "What this is (and
  isn't)" above
- **Telegram**: fully automatic — a Queued Telegram post gets a **Send**
  button (on the Queue page, replacing the generic Start button just for
  Telegram) that sends it via the official Bot API, then immediately
  records the real outcome: Posted with Telegram's own message id
  captured, or Failed with Telegram's own error message if it's rejected
  (a missing/wrong bot token, a wrong chat/channel id, etc. — never a
  crash, always a clear reason)
- **TikTok**: since TikTok's own posting API needs an app-audit approval
  most users won't have, this is a manual workflow by default — generate
  a recruitment graphic (English or Arabic, with correct right-to-left
  text) from the Queue page with one click, download it, post it from
  your phone, then mark what happened. Any post sitting in Processing
  with nowhere else to resolve it (TikTok, or anything Started by hand)
  now gets generic **Mark Posted**/**Mark Failed** buttons too
- **Scheduler**: opt a Queued post into fully unattended sending with a
  **Schedule** button (only for posts that already have a scheduled
  time) — a background ticker checks every 60 seconds (configurable) for
  posts whose time has come. Telegram posts get genuinely sent with no
  one watching; Facebook/TikTok posts (which can't be sent unattended)
  are flagged **Manual Action Required** instead of silently sitting
  overdue. **Unschedule** reverses it any time before it fires
- **Calendar**: a read-only week-at-a-glance view of everything with a
  scheduled time, regardless of status or platform — for orientation,
  not action; every action still lives on the Queue page
- **Analytics**: log views/clicks/messages/applications/interviews/hires
  by hand for any job + destination (optionally tied to one specific
  post) — there's no automated metrics collection from any platform, so
  every number here is one you typed in. See a conversion funnel, a
  performance breakdown by destination, and — for posts logged against
  a specific template — which tone/template is actually converting
- **Backup/restore**: `backup.bat` copies the live database into
  `backups\` with a timestamp (keeping the most recent 10 automatically);
  `restore.bat` lists what's available and restores one, always taking a
  fresh safety backup of the current database first so a restore is
  itself reversible
- `pytest` test suite: 205 tests across settings, schema, repository,
  service, and API layers for every feature above, plus real (unmocked)
  file-generation tests for the TikTok visual generator and the backup/
  restore scripts
- `setup.bat` / `run.bat` for one-command setup and startup on Windows

All 14 planned phases are complete. `PROJECT_STATUS.md` has the full
history — design decisions, real bugs found and fixed along the way, and
what was deliberately left out (TikTok's audit-gated API, AI-assisted
content) and why.

### Using the Jobs page

Open the dashboard, click **Jobs** in the sidebar. "Create new job" is
collapsed at the top — expand it, fill in a title (the only required
field) and whatever else you have, submit. Below that: search, a status
filter, and an "include archived" toggle, then the list itself. Each job
expands to show details and four actions — **Edit** (opens the full form,
including changing status directly), **Duplicate** (makes a fresh Draft
copy, useful for reposting similar roles), **Close** (position filled or
cancelled), and **Archive** (hide it from your default view without
deleting it — independent of status, so you can archive a closed job or a
draft you dropped).

### Using the Destinations page

Click **Destinations** in the sidebar. "Add new destination" works the same
way as Jobs' create form. Tags go in a single comma-separated field (e.g.
`Cairo, Call Center, English Jobs`); reusing a tag name (case-insensitive)
attaches the existing tag instead of creating a duplicate.

**CSV import/export** is in its own expander. Import expects the columns
`platform, name, url, category, location, audience, language,
posting_method, active, notes, tags` — `posting_method` and `active` are
optional (sensible defaults apply), and multiple tags in one cell are
separated with `|` (e.g. `Cairo|Call Center`), not `,`, since commas are
already the CSV delimiter. A bad row (unrecognized platform, missing name)
is reported individually and skipped — it doesn't block the rest of the
file from importing. `samples/sample_destinations.csv` in this project has
20 fully fictional example rows in the right format if you want to see it
work before entering your real groups/channels.

Each destination expands to show its details and three actions — **Edit**,
**Activate/Deactivate** (toggle without touching anything else), and
**Delete** (asks for confirmation first — this one's permanent).

### Using the Templates page

Click **Templates** in the sidebar. An "Available variables" reference is
at the top — every variable maps to a Job field (`{{job_title}}`,
`{{company}}`, `{{salary}}`, and so on; `{{salary}}` uses the job's own
salary text if set, otherwise a formatted min–max range). Anything else
you type in `{{double braces}}` gets left exactly as written in the
rendered output and flagged as unrecognized — that's almost always a typo,
and you'll see the warning immediately after saving, not only when you
happen to preview that template.

**Preview a template against a job** (its own expander) is the fastest way
to check a template actually reads well — pick any template and any job
from the two dropdowns and click Render. Each template card also shows
**Edit**, **Activate/Deactivate**, and **Delete** (with confirmation),
same pattern as Jobs and Destinations.

### Using the Post Creator page

Click **Post Creator** in the sidebar. Two ways to generate content:

**Generate posts** — pick a job and one or more destinations, leave the
template on "Auto-select per platform" (it picks a suitable active
template per destination, preferring a language match if the destination
has one set), and click Generate. Selecting destinations across different
platforms in one go is fine — each gets its own platform-appropriate
template automatically.

**Generate variations** — pick a job and *one* destination, then pick
several templates that share that destination's platform (e.g. compare
the Professional, Urgent, and Fresh Graduates Facebook templates for the
same job) to see them side by side before deciding what to actually use.

Either way, results land in **Generated posts** below, where you can
expand any post to see its content in a code block — hover it for a
built-in copy button — edit the text by hand if you want to tweak the
auto-generated version, or delete it (with confirmation). Filter the list
by job, destination, or status.

### Using the Queue page

Click **Queue** in the sidebar. **Create a queue** works like Post
Creator's generate section, plus a posting window: "Start now" or pick a
specific date/time, and a delay between each destination (defaults to 5
minutes) — the first destination gets the start time, the second gets
start + delay, and so on. Unlike Post Creator, these land as **Queued**,
not Draft.

If a destination has a workflow flag — it's inactive, hasn't cleared its
own cooldown, is at its daily limit, or already has a queued post for this
job — you'll see a warning, but it's queued anyway; these are your own
internal safeguards (set per-destination when you create/edit it), not
something the app enforces against you.

Already have Draft posts from Post Creator? **Queue an existing draft**
lists them with a one-click "Queue this" button instead of regenerating
from scratch — or click **Queue all N drafts** above the list to promote
every one of them in a single click, staggered the same way "Create a
queue" staggers a fresh batch (so bulk-promoting 50 drafts doesn't
schedule all 50 for the same instant).

**Progress** shows a live count of posts by status. **Manage queue** is
where the day-to-day happens: filter by job/destination/status, and each
post shows **Start** (Queued → Processing), **Pause/Resume** (independent
of status — a paused post stays wherever it is and the Scheduler skips
it), **Skip**, **Retry** (only shown when relevant — you can't retry a
post that isn't Failed), and **Open destination** (opens the group/channel
URL in a new tab).

A Queued post against a **Telegram** destination shows **Send** instead
of **Start** — one click sends it via the Bot API and immediately shows
the real result (Posted or Failed with Telegram's own error message),
rather than just flipping its status and leaving you to do something else
next. Facebook posts are unaffected — they keep the plain **Start**
button described above.

A post against a **TikTok** destination shows a **Generate visual**
button (becomes **Regenerate visual** with a thumbnail preview once one
exists) — produces a recruitment graphic sized for TikTok, with correct
right-to-left text if the job's title/company/location is in Arabic.
Download it and post it yourself; there's no automated TikTok posting
(see "What this is (and isn't)" above). Once you've started a post
(**Start**, same button as every other platform) and posted it by hand,
any post sitting in **Processing** — TikTok or otherwise — shows generic
**Mark Posted**/**Mark Failed** buttons to record what actually
happened.

A Queued post with a scheduled time shows **Schedule** — opts it into
the background ticker actually sending it (Telegram) or flagging it
Manual Action Required once due (Facebook/TikTok) with nobody watching.
**Unschedule** reverses it any time before it fires. See "Using the
Calendar page" and "Using the Analytics page" below for the two other
new pages this phase added.

### Using the Facebook Assistant page

Click **Facebook Assistant** in the sidebar. This is the one page that
doesn't look like the others — instead of a filterable list, it walks you
through your Queued Facebook posts one at a time. Land on a post and it
immediately opens the destination group in your browser and copies the
post text to your clipboard — paste (Ctrl+V) and click Post yourself in
that browser tab.

Once you've posted (or decided not to), pick one:

- **Posted** — marks it Posted and moves to the next one
- **Skip** — marks it Skipped (you won't post this one) and moves on
- **Failed** — marks it Failed; there's an optional reason field above the
  buttons if you want to note why (e.g. "needs admin approval")
- **Pause** — sets it aside for later without deciding either way; find it
  again later via the Queue page's Resume action, then revisit this page
- **Next** — leaves it exactly as-is and shows you a different one, no
  decision recorded; you'll see it again once you've been through
  everything else

Keyboard shortcuts for the first four (not while typing in the reason
field): **Enter** = Posted, **S** = Skip, **P** = Pause, **N** = Next.

If the automatic clipboard copy doesn't work (this needs `xclip` or `xsel`
on Linux — nothing extra on Windows, which is the primary target), the
post content is always shown in a code block you can copy manually, and an
**Open destination** button is there as a fallback if the browser doesn't
open on its own.

### Using the Calendar page

Click **Calendar** in the sidebar for a week-at-a-glance view of every
post with a scheduled time, regardless of status or platform. Navigate
with **← Previous week** / **Next week →**. This page is read-only on
purpose — every action a post might need already has a home on the Queue
page or the Facebook Assistant; duplicating them here would just create
two places that could disagree with each other.

### Using the Analytics page

Click **Analytics** in the sidebar. There's no automated metrics
collection from any platform — Facebook and TikTok have no API access at
all, and Telegram's Bot API can confirm a message sent but doesn't expose
view/click analytics. Every number here is one you log by hand.

**Log metrics** — pick a job, a destination, and a date (defaults to
today), then enter whatever numbers you have. Re-submitting the same
job + destination + date + post updates that entry rather than creating
a duplicate, so correcting an earlier number just means filling in the
form again with the right figure. If you're logging numbers for a
*specific* post (rather than a general daily total for that
job/destination), note its post ID — that's what makes the by-template
breakdown below possible.

Below the form: a **funnel** (views → clicks → messages → applications →
interviews → hires, with the conversion rate between each stage),
**performance by destination**, and **performance by template** — the
last one only counts metrics you logged against a specific post, since a
general daily total can't be attributed to one template's wording.

## Requirements

- Windows 10/11
- Python 3.11 or newer, with "Add python.exe to PATH" checked during install
  ([python.org/downloads](https://www.python.org/downloads/))
- No C++ build tools needed — every Phase 1 dependency ships prebuilt
  Windows wheels
- Git and VS Code: optional, not required to run the app

## Installation (Windows)

1. Download/clone this project folder.
2. Double-click `setup.bat` (or run it from a terminal in the project
   folder). It will:
   - Check for Python
   - Create a virtual environment in `venv\`
   - Install everything in `requirements.txt`
   - Copy `.env.example` to `.env` if you don't already have one
   - Create the `data\`, `logs\`, and `backups\` folders
   - Initialize the SQLite database
3. Double-click `run.bat`. It starts the API (port 8000) and the dashboard
   (port 8501) in separate windows and opens your browser to
   `http://127.0.0.1:8501`.

To stop the app, close the two terminal windows `run.bat` opened (or press
`Ctrl+C` inside each).

See "Backups" below for `backup.bat`/`restore.bat` — separate from
`setup.bat`/`run.bat`, run only when you actually want to back up or
restore.

> **Note:** `run.bat` and `setup.bat` are written to standard Windows batch
> conventions but were developed and tested in a Linux environment (this
> project was built through Claude, which doesn't have a Windows machine to
> test `.bat` execution directly). The Python code inside them has been
> fully tested; if either script itself misbehaves on your machine, tell me
> what happened and I'll fix it.

## Environment variables

See `.env.example` for the full list with comments. The short version:

| Variable | Required? | Purpose |
|---|---|---|
| `DATABASE_URL` | No | Defaults to `data/recruitment.db`; override to point elsewhere |
| `LOG_LEVEL`, `LOG_FILE` | No | Logging configuration |
| `API_HOST`, `API_PORT` | No | Where the FastAPI backend listens (default `127.0.0.1:8000`) |
| `STREAMLIT_PORT` | No | Where the dashboard listens (default `8501`) |
| `TELEGRAM_BOT_TOKEN` | Only for Telegram (Phase 8) | From @BotFather |
| `AI_API_KEY`, `AI_PROVIDER` | No | Placeholders only — no AI-assisted feature has been built yet (see the cost table above) |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET` | No | Placeholders only — no code uses them yet (see "What this is (and isn't)") |
| `SCHEDULER_ENABLED` | No | Default `true`; the background ticker that sends due Scheduled posts |
| `SCHEDULER_INTERVAL_SECONDS` | No | Default `60`; how often the ticker checks for due posts |

## Running tests

```
venv\Scripts\activate
pytest -q
```

## Backups

```
backup.bat
```

Copies the live database into `backups\` with a timestamp, keeping the
most recent 10 automatically (older ones are deleted). Safe to run any
time, including while the app is up.

```
restore.bat
```

With no arguments, lists what's available. Run it again with a filename
to restore that one — **close `run.bat`'s two windows first**; replacing
the database file while the app has it open can leave things
inconsistent. Restoring always takes a fresh safety backup of the
current database first, so a restore is itself reversible if you picked
the wrong one.

## Database schema

Six tables, all genuinely in use: `jobs`, `destinations`, `tags` (with a
`destination_tags` join table for many-to-many tagging), `post_templates`,
`posts`, and `application_metrics` (Phase 11 — manual metrics logging).
`jobs` has an `archived` flag (Phase 2) and `posts` has a `paused` flag
(Phase 6), both independent of their respective `status` fields — see
`PROJECT_STATUS.md` for why in each case. 7 `post_templates` rows are
seeded automatically on first run (see "Using the Templates page" above);
`posts` rows move through
`Draft → Queued → (Scheduled) → Processing → Posted/Failed/Skipped`, with
`Manual Action Required` for a Scheduled Facebook/TikTok post whose time
came due with nobody watching (see "Using the Queue page" above). Full
column lists are in `PROJECT_STATUS.md`.

Destinations import/export uses `samples/sample_destinations.csv` as a
format reference — see "Using the Destinations page" above.

## Troubleshooting

- **"Python was not found"** — reinstall Python and check "Add python.exe to
  PATH", or restart your terminal after installing.
- **Dashboard shows "API status: Offline"** — the FastAPI window either
  didn't start or crashed; check its terminal window for an error, and check
  `logs\app.log`.
- **Port already in use** — another program is using 8000 or 8501; change
  `API_PORT` / `STREAMLIT_PORT` in `.env`.

## Security notes

- No social-media passwords are ever stored — Facebook uses your normal
  logged-in browser session; nothing else needs credentials except the
  Telegram bot token and, optionally, an AI API key.
- Secrets live only in `.env`, which is git-ignored.
- This is a local, single-user tool with no login system — it isn't
  designed to be exposed beyond `127.0.0.1`. If you ever want to access it
  from another device, that needs authentication added first; ask before
  assuming it's safe to do.
- **If you ran this project before Phase 12 with a real Telegram bot
  token configured**: a dependency's own internal logging (not this
  project's code) was writing that token into `logs\app.log` in plain
  text. This is fixed now, but a token that was already logged before
  the fix should be treated as exposed — rotate it via @BotFather if
  that applies to you. See `PROJECT_STATUS.md`'s Phase 12 notes for the
  full account.
- `backup.bat` copies the whole database file, including anything
  sensitive you've entered (job details, destination info, logged
  metrics) — treat backup files the same way you'd treat the live
  database itself.

## Development

Contributions/changes follow the phase plan in `PROJECT_STATUS.md`. Before
modifying existing code: read `PROJECT_STATUS.md`, inspect the file you're
about to change, understand what depends on it, then make the smallest
change that accomplishes the goal.
