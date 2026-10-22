# Mapster outreach pipeline

Setup: `pip install -r requirements.txt`, copy `.env.example` to `.env`, fill `GMAIL_APP_PASSWORD` (and `TEST_EMAIL`).
Control panel: `python -m mapster ui` (or `python ui.py`) opens http://localhost:8765.
CLI: `python -m mapster draft | approve --all | run [--dry] | test <email> | status` (`pipeline.py` still works).
Tests: `python -m pytest tests`.

Flow in the panel: Add contact (Client or Network) > Generate email > Preview > Approve or "Approve and send now".
Follow ups go out as replies in the same thread every 2 days until the person replies, bounces, or you press Stop.
Clients get the proposal PDF with their name on the cover. Network contacts get the pitch deck.
Edit follow up wording under "Follow up messages". Autopilot sends approved mails and due follow ups (inside sending hours) while the panel is open.

## Layout

```
mapster/
  config.py     settings from .env (one frozen dataclass)
  store.py      SQLite state (data/mapster.db), replaces state.json + settings.json
  contacts.py   contacts.csv read/write
  text.py       clean() and first_name()
  llm.py        Anthropic API, or local `claude` CLI fallback
  writer.py     prompts + first email drafting
  followups.py  editable follow up pool
  mailer.py     SMTP send, IMAP reply/bounce detection
  pdfgen.py     per recipient proposal PDF
  service.py    all pipeline actions (shared by CLI and API)
  jobs.py       one-at-a-time background jobs + log capture
  api.py        FastAPI endpoints for the panel
  static/index.html   the panel UI
```

`legacy/` holds the original scripts and state files as a backup. Delete it once you're happy.
