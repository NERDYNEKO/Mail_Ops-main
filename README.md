# Mapster Mail Ops

**An autonomous cold-outreach pipeline for Mapster.** It drafts personalised emails with Claude, attaches a per-recipient proposal PDF, sends them politely over Gmail, and keeps following up in the same thread until the person replies, bounces, or you stop it.

You keep a human in the loop: nothing is sent until you preview and approve it.

---

## Table of contents

- [What it does](#what-it-does)
- [Two implementations](#two-implementations)
- [Repository layout](#repository-layout)
- [Quick start: Python app](#quick-start-python-app)
- [Quick start: MERN web app](#quick-start-mern-web-app)
- [Configuration](#configuration)
- [How the pipeline works](#how-the-pipeline-works)
- [API overview](#api-overview)
- [Testing](#testing)
- [Security and privacy](#security-and-privacy)
- [Troubleshooting](#troubleshooting)

---

## What it does

1. **Add contacts** one by one or import a CSV. Each contact is either a **Client** (an event or exhibition organiser) or **Network** (a partner or connector).
2. **Generate** a personalised email. Claude writes it from the contact's org, event and "about" text, using editable prompts.
3. **Preview and edit** the subject, body and the attached PDF.
4. **Approve** (or "Approve and send now"). Sends are spaced out randomly (90 to 240 seconds by default), capped per day, and limited to sending hours.
5. **Follow up automatically.** Short follow-ups go out as replies in the same thread every few days. They stop when the person replies, the address bounces, you press Stop, or the per-person limit is reached.
6. **Attachments:** Clients get the proposal PDF with their name on the cover. Network contacts get the pitch deck.
7. **Autopilot** (optional) sends approved mails and due follow-ups on a schedule, and checks IMAP for replies and bounces.

## Two implementations

The repo contains two versions of the same product. They share the same ideas, settings and content.

| | Python app (`mapster/`) | MERN web app (`mapster-web/`) |
|---|---|---|
| Stack | FastAPI, SQLite, single-file HTML panel | React (Vite, TypeScript), Express, MongoDB, BullMQ + Redis |
| Best for | Running locally on one machine | Hosting for a team, always-on |
| Auth | None (local only, binds to localhost) | Admin login with JWT in an httpOnly cookie |
| Job handling | One background job at a time, in process | Durable queue, survives restarts, retries on failure |
| PDF rendering | PyMuPDF | Chromium via puppeteer-core |
| Run | `python -m mapster ui` | `docker compose up -d --build` |

The original single-file scripts are kept in `legacy/` as a backup. Delete them when you no longer need them.

## Repository layout

```
.
├── mapster/                  Python app (package)
│   ├── config.py             settings from .env (one frozen dataclass)
│   ├── store.py              SQLite state in data/mapster.db
│   ├── contacts.py           contacts.csv read/write
│   ├── text.py               clean() and first_name() helpers
│   ├── llm.py                Anthropic API, with local `claude` CLI fallback
│   ├── writer.py             prompts and first-email drafting
│   ├── followups.py          editable follow-up message pool
│   ├── mailer.py             SMTP send, IMAP reply/bounce detection
│   ├── pdfgen.py             per-recipient proposal PDF
│   ├── service.py            all pipeline actions (shared by CLI and API)
│   ├── jobs.py               one-at-a-time background jobs + log capture
│   ├── api.py                FastAPI endpoints for the panel
│   ├── static/index.html     the control panel UI
│   └── __main__.py           command line entry point
├── mapster-web/              MERN web app
│   ├── server/               Express API + BullMQ worker (TypeScript)
│   │   ├── src/
│   │   │   ├── index.ts, routes.ts, auth.ts, config.ts, queue.ts, logger.ts
│   │   │   ├── models/       Mongoose models (Contact, Activity, misc)
│   │   │   ├── services/     pipeline, writer, mailer, followups, pdf, text
│   │   │   └── content/      prompts.json, followups.json
│   │   ├── scripts/migrate-legacy.ts   import old Python data once
│   │   └── tests/            vitest tests
│   ├── client/               React + Vite UI (App, Drawer, Templates)
│   ├── assets/               logos, pitch deck, proposal.html template
│   ├── Dockerfile
│   └── docker-compose.yml    app + MongoDB + Redis
├── assets/                   shared logos, pitch deck, proposal template
├── tests/                    Python tests (pytest)
├── legacy/                   original scripts (backup)
├── followup_templates.json   editable follow-up wording (Python app)
├── pipeline.py, ui.py        shims: old commands still work
├── Mapster_Pilot_Proposal_New.pdf   sample proposal
├── requirements.txt          Python dependencies
└── .env.example              settings template
```

## Quick start: Python app

Requires Python 3.10+.

```bash
pip install -r requirements.txt
cp .env.example .env          # then fill GMAIL_APP_PASSWORD (and TEST_EMAIL)
python -m mapster ui          # opens http://localhost:8765
```

Command line:

```bash
python -m mapster draft [--only a@x.com]      # write emails for new contacts
python -m mapster approve --all               # approve drafts (or list emails)
python -m mapster run [--dry] [--force] [--only a@x.com]
python -m mapster test a@x.com                # send that email to TEST_EMAIL only
python -m mapster status
```

`python pipeline.py ...` and `python ui.py` still work.

**Typical flow in the panel:** Add contact (Client or Network) → Generate email → Preview → Approve or "Approve and send now". Edit follow-up wording under "Follow up messages". Autopilot sends approved mails and due follow-ups, inside sending hours, while the panel is open.

## Quick start: MERN web app

### Production (Docker)

```bash
cd mapster-web
cp .env.example .env     # set JWT_SECRET, ADMIN_EMAIL, ADMIN_PASSWORD, GMAIL_APP_PASSWORD, ANTHROPIC_API_KEY
docker compose up -d --build
```

Open http://localhost:8080 and sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`. Put it behind HTTPS (Caddy, nginx or your host's proxy) before exposing it to the internet. Generate a strong secret with `openssl rand -hex 32`.

### Development

```bash
cd mapster-web
docker compose up -d mongo redis            # databases only
cd server && cp ../.env.example .env && npm install && npm run dev   # API + worker on :8080
cd ../client && npm install && npm run dev                           # UI on :5173, proxies /api
```

Checks: `npm run typecheck && npm test` in `server/`, `npm run build` in `client/`.
Import old Python data once: `cd server && npm run migrate:legacy`.

## Configuration

All settings come from environment variables (`.env`). Never commit your real `.env`.

| Variable | Purpose | Default |
|---|---|---|
| `GMAIL_USER` | Sending Gmail address | `mapster.officials@gmail.com` |
| `GMAIL_APP_PASSWORD` | Google App Password (Account → Security → 2-Step Verification → App passwords) | required |
| `TEST_EMAIL` | Your own address, used by "Send a test to myself" | empty |
| `ANTHROPIC_API_KEY` | Claude API key. Leave empty (Python app) to use your Claude Code login | empty |
| `DAILY_CAP` | Max emails per day | `25` |
| `DELAY_MIN_SEC` / `DELAY_MAX_SEC` | Random gap between sends | `90` / `240` |
| `FOLLOWUP_GAP_DAYS` | Days between the main mail and each follow-up | `2` |
| `FOLLOWUP_MAX` | Safety limit on follow-ups per person | `10` |
| `SEND_START_HOUR` / `SEND_END_HOUR` | Sending window (local hours) | `9` / `19` |
| `TZ_NAME` | Timezone for the window | `Asia/Kolkata` |
| `AUTOPILOT_EVERY_MIN` | How often autopilot runs | `30` |
| `JWT_SECRET` | Web app only: signs login cookies | required |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Web app only: admin account, created on first start | required |
| `PORT`, `NODE_ENV` | Web app only | `8080`, `production` |

The web app also uses `MONGO_URL` and `REDIS_URL` (set for you in `docker-compose.yml`).

## How the pipeline works

```
 contact ──► draft (Claude) ──► preview/edit ──► approve ──► queue ──► SMTP send
                                                                          │
              stop on reply / bounce / Stop ◄── IMAP check ◄── follow-ups every N days
```

- **Drafting.** Prompts live in `mapster-web/server/src/content/prompts.json` (web) and `mapster/writer.py` (Python). Output is cleaned by `text.py` before use.
- **Threading.** Follow-ups reuse the original message ID so they appear as replies in the same thread.
- **Follow-up pool.** Wording is editable (`followup_templates.json` or the "Templates" screen) and uses placeholders such as `{first}` and `{event}`. Selection is stable per contact so the same person doesn't get the same line twice.
- **No double sends (web).** A contact is atomically claimed with a `sending` flag before SMTP, so a retry can never send twice.
- **Rate and window limits.** Daily cap, random delay between sends and a sending-hours window keep volume human-looking and compliant with Gmail limits.
- **Autopilot.** Checks replies and bounces over IMAP first, then queues approved emails and due follow-ups.
- **PDFs.** Rendered per recipient with their name on the cover and cached by name.

## API overview

**Python app** (`mapster/api.py`, local only): `GET /api/items`, `GET /api/preview`, `GET/POST /api/templates`, `GET /pdf/{email}`, and `POST /api/` `save`, `contact`, `delete`, `status`, `stop`, `redraft`, `approve_all`, `autopilot`, `bulk`, `gen`, `send_one`, `test`, `run`.

**Web app** (`mapster-web/server/src/routes.ts`, all under `/api`, auth required except login and health):

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | health check |
| POST | `/auth/login`, `/auth/logout` · GET `/auth/me` | session |
| GET | `/meta`, `/activity` | dashboard data |
| PUT | `/settings/autopilot` | toggle autopilot |
| GET/PUT | `/templates` | follow-up pool |
| GET/POST | `/contacts` | list, create |
| PUT/DELETE | `/contacts/:id` | update, remove |
| POST | `/contacts/import` · GET `/contacts-export.csv` | CSV in/out |
| PUT | `/contacts/:id/email` | edit drafted email |
| GET | `/contacts/:id/preview`, `/contacts/:id/attachment` | preview, PDF |
| POST | `/contacts/:id/<action>`, `/bulk`, `/run` | generate, approve, send, stop, bulk and run |

## Testing

```bash
python -m pytest tests                       # Python app
cd mapster-web/server && npm test            # web server (vitest)
cd mapster-web/server && npm run typecheck
cd mapster-web/client && npm run build
```

## Security and privacy

- Secrets live only in `.env`, which is git-ignored. Only `.env.example` templates (with empty secrets) are committed.
- Runtime data (`data/`, `*.db`, `contacts.csv`, `state.json`, generated PDFs in `out/`) is git-ignored because it contains personal contact information.
- Web app: JWT in an httpOnly, SameSite=strict cookie, rate-limited login, Helmet security headers. Serve it over HTTPS.
- Use a Gmail **App Password**, never your account password. If a key or password is ever committed by mistake, rotate it immediately.
- Be considerate: send only to relevant, legitimate contacts, honour replies and unsubscribe requests, and follow the anti-spam laws that apply to you.

## Troubleshooting

- **SMTP login fails.** Enable 2-Step Verification and create an App Password; paste it without spaces.
- **No emails drafted.** Set `ANTHROPIC_API_KEY`, or (Python app) make sure the `claude` CLI is logged in.
- **Nothing sends.** Check you are inside `SEND_START_HOUR`–`SEND_END_HOUR`, the daily cap isn't reached, and contacts are approved.
- **PDF fails (web).** The container needs Chromium; use the provided `Dockerfile`.
- **Port in use.** Python panel uses `8765`, web app `8080`, Vite dev server `5173`.
