"""SQLite storage for outreach state. Replaces state.json / settings.json.

SQLite gives atomic writes and safe access from the UI thread and the send job at the
same time, which the old read-modify-write JSON file did not.
"""
import json
import sqlite3
from contextlib import contextmanager

from .config import cfg

SCHEMA = """
CREATE TABLE IF NOT EXISTS outreach (
    email TEXT PRIMARY KEY,
    contact TEXT NOT NULL,
    status TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    sent TEXT NOT NULL DEFAULT '[]',
    message_ids TEXT NOT NULL DEFAULT '[]',
    followups INTEGER NOT NULL DEFAULT 0,
    stopped INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
JSON_COLS = ("contact", "sent", "message_ids")


@contextmanager
def _conn():
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(cfg.db_path, timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    try:
        with db:  # commit or roll back
            yield db
    finally:
        db.close()


def _row(r) -> dict:
    d = dict(r)
    for k in JSON_COLS:
        d[k] = json.loads(d[k])
    d["stopped"] = bool(d["stopped"])
    return d


def init():
    with _conn() as db:
        db.executescript(SCHEMA)
        empty = db.execute("SELECT COUNT(*) FROM outreach").fetchone()[0] == 0
    legacy = cfg.root / "state.json"
    if empty and legacy.exists():  # one time import of the old JSON state
        for email, s in json.loads(legacy.read_text(encoding="utf-8")).items():
            put(email, s)
        legacy.rename(legacy.with_suffix(".json.migrated"))
    old_settings = cfg.root / "settings.json"
    if old_settings.exists():
        set_setting("autopilot", json.loads(old_settings.read_text()).get("autopilot", False))
        old_settings.rename(old_settings.with_suffix(".json.migrated"))


def all_items() -> dict:
    with _conn() as db:
        return {r["email"]: _row(r) for r in db.execute("SELECT * FROM outreach ORDER BY rowid")}


def get(email: str) -> dict | None:
    with _conn() as db:
        r = db.execute("SELECT * FROM outreach WHERE email=?", (email.lower(),)).fetchone()
    return _row(r) if r else None


def put(email: str, s: dict):
    row = {**s, **{k: json.dumps(s[k], ensure_ascii=False) for k in JSON_COLS},
           "stopped": int(bool(s.get("stopped"))), "email": email.lower()}
    with _conn() as db:
        db.execute("""INSERT OR REPLACE INTO outreach
            (email, contact, status, subject, body, sent, message_ids, followups, stopped)
            VALUES (:email, :contact, :status, :subject, :body, :sent, :message_ids, :followups, :stopped)""", row)


def update(email: str, **fields):
    """Patch one record. Missing records are ignored."""
    s = get(email)
    if s:
        put(email, {**s, **fields})


def delete(email: str):
    with _conn() as db:
        db.execute("DELETE FROM outreach WHERE email=?", (email.lower(),))


def rename(old: str, new: str):
    s = get(old)
    if s:
        delete(old)
        put(new, {**s, "contact": {**s["contact"], "email": new.lower()}})


def get_setting(key: str, default=None):
    with _conn() as db:
        r = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r["value"]) if r else default


def set_setting(key: str, value):
    with _conn() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, json.dumps(value)))
