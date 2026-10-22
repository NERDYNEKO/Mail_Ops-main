"""Core pipeline actions. Used by both the CLI and the web API."""
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from . import contacts, followups, mailer, store
from .config import DATE_FMT, cfg
from .text import clean
from .writer import SIGNATURE, write_first

log = logging.getLogger("mapster")
EDITABLE = ("drafted", "approved")


def shown_status(s: dict) -> str:
    return "stopped" if s["stopped"] and s["status"] in ("approved", "sent") else s["status"]


def cover_name(c: dict) -> str:
    return c.get("cover_name") or c.get("event") or c.get("org") or c.get("name") or ""


def attachment_for(s: dict) -> tuple[Path, str]:
    """Clients get the proposal with their name on the cover, network gets the deck."""
    c = s["contact"]
    if c.get("category") == "network":
        return cfg.deck, "Mapster_Pitch_Deck.pdf"
    from .pdfgen import make_proposal
    out = cfg.out_dir / f"Mapster_Proposal_{contacts.slug(c['email'])}.pdf"
    return make_proposal(cover_name(c), out), "Mapster_Pilot_Proposal.pdf"


def _prewritten(email: str) -> dict | None:
    f = cfg.written_dir / f"{contacts.slug(email)}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def _new_record(c: dict, subject: str, body: str) -> dict:
    return {"contact": c, "status": "drafted", "subject": subject, "body": body + "\n\n" + SIGNATURE,
            "sent": [], "message_ids": [], "followups": 0, "stopped": False}


# ---------- draft / approve ----------
def draft(only: list[str] | None = None):
    only = {x.lower() for x in only or []}
    for c in contacts.load():
        e = c["email"].lower()
        if store.get(e) or (only and e not in only):
            continue
        try:
            if (pre := _prewritten(e)):
                mail = {"subject": clean(pre["subject"]), "body": clean(pre["body"])}
            else:
                log.info("Writing email for %s ...", e)
                mail = write_first(c)
        except Exception as ex:
            log.error("FAILED for %s: %s", e, ex)
            continue
        store.put(e, _new_record(c, mail["subject"], mail["body"]))
        log.info("Drafted %s", e)
    log.info("Done.")


def approve(emails: list[str] | None = None):
    """Approve the given drafts, or every draft when emails is None."""
    wanted = None if emails is None else {x.lower() for x in emails}
    for e, s in store.all_items().items():
        if s["status"] == "drafted" and (wanted is None or e in wanted):
            store.update(e, status="approved")
            log.info("Approved %s", e)


# ---------- send ----------
def in_window() -> bool:
    return cfg.send_hours[0] <= datetime.now().hour < cfg.send_hours[1]


def _followup_due(s: dict) -> bool:
    return (s["status"] == "sent" and not s["stopped"] and s["followups"] < cfg.followup_max
            and datetime.now() - datetime.strptime(s["sent"][-1], DATE_FMT) >= timedelta(days=cfg.followup_gap_days))


def _recorder(email: str, patch):
    """Callback run right after a message is accepted by SMTP: log the send time and Message-ID."""
    def done(mid: str):
        s = store.get(email)
        store.update(email, sent=s["sent"] + [datetime.now().strftime(DATE_FMT)],
                     message_ids=s["message_ids"] + [mid], **patch(s))
    return done


def run(dry: bool = False, force: bool = False, only: list[str] | None = None):
    only = {x.lower() for x in only or []}
    if not (dry or force or only) and not in_window():
        log.info("Outside sending hours (%d:00 to %d:00). Nothing sent.", *cfg.send_hours)
        return
    mailer.check_replies()
    items = store.all_items()
    today = datetime.now().strftime("%Y-%m-%d")
    budget = max(0, cfg.daily_cap - sum(1 for s in items.values() for t in s["sent"] if t[:10] == today))
    queue = []

    for e, s in items.items():
        if len(queue) >= budget:
            break
        if (only and e not in only) or s["stopped"]:
            continue
        if s["status"] == "approved":
            if dry:
                log.info("[dry] first email to %s: %s", e, s["subject"])
                continue
            msg = mailer.build(e, s["subject"], s["body"], attachment_for(s))
            queue.append((e, msg, _recorder(e, lambda s: {"status": "sent"})))
        elif _followup_due(s):
            n = s["followups"] + 1
            if dry:
                log.info("[dry] follow up %d due for %s", n, e)
                continue
            subj = s["subject"] if s["subject"].lower().startswith("re:") else "Re: " + s["subject"]
            body = followups.followup_text(s["contact"], n) + "\n\n" + SIGNATURE
            msg = mailer.build(e, subj, body, None, s["message_ids"][0], s["message_ids"][:1])
            queue.append((e, msg, _recorder(e, lambda s: {"followups": s["followups"] + 1})))

    if dry:
        return
    if not queue:
        log.info("Nothing to send.")
        return
    if not cfg.gmail_password:
        raise SystemExit("Set GMAIL_APP_PASSWORD in .env first.")
    log.info("Sending %d email(s)...", len(queue))
    mailer.send(queue, delay=len(queue) > 1)
    log.info("Done.")


def send_test(email: str):
    s = store.get(email)
    if not s:
        raise SystemExit("No draft for that email.")
    if not (cfg.test_email and cfg.gmail_password):
        raise SystemExit("Set TEST_EMAIL and GMAIL_APP_PASSWORD in .env first.")
    msg = mailer.build(cfg.test_email, "[TEST] " + s["subject"], s["body"], attachment_for(s))
    mailer.send([(cfg.test_email, msg, lambda mid: None)], delay=False)


def status_lines() -> tuple[list[str], dict]:
    lines, counts = [], {}
    for e, s in store.all_items().items():
        st = shown_status(s)
        counts[st] = counts.get(st, 0) + 1
        lines.append(f"{st:9} follow ups {s['followups']}  {e}")
    return lines, counts


# ---------- views and edits used by the web panel ----------
def next_due(s: dict | None) -> str | None:
    if not s or s["status"] != "sent" or s["stopped"] or s["followups"] >= cfg.followup_max:
        return None
    return (datetime.strptime(s["sent"][-1], DATE_FMT) + timedelta(days=cfg.followup_gap_days)).isoformat()


def strip_sig(body: str) -> str:
    return body[:-len(SIGNATURE)].rstrip() if body.endswith(SIGNATURE) else body


def items() -> list[dict]:
    state, out = store.all_items(), []
    for c in contacts.load():
        e = c["email"].lower()
        s, w = state.get(e), _prewritten(e) or {}
        subject, body = (s["subject"], strip_sig(s["body"])) if s else (w.get("subject", ""), w.get("body", ""))
        out.append({"contact": c, "email": e, "category": c["category"],
                    "status": shown_status(s) if s else ("written" if w else "no draft"),
                    "has_state": bool(s), "stopped": bool(s and s["stopped"]),
                    "subject": subject, "body": body, "sent": s["sent"] if s else [],
                    "followups_sent": s["followups"] if s else 0, "next_due": next_due(s)})
    return out


def preview(email: str) -> dict:
    s = store.get(email)
    if not s:
        return {"error": "No draft yet. Click Generate email first."}
    c = s["contact"]
    fname = "Mapster_Pitch_Deck.pdf" if c.get("category") == "network" else "Mapster_Pilot_Proposal.pdf"
    subj = s["subject"] if s["subject"].lower().startswith("re:") else "Re: " + s["subject"]
    n = s["followups"] + 1
    return {"from": f"{cfg.from_name} <{cfg.gmail_user}>", "to": f"{c.get('name', '')} <{c['email']}>",
            "subject": s["subject"], "body": s["body"], "attachment": fname, "status": shown_status(s),
            "followup_subject": subj, "followup_body": followups.followup_text(c, n) + "\n\n" + SIGNATURE,
            "followup_n": n, "cover": cover_name(c), "can_test": bool(cfg.test_email and cfg.gmail_password)}


def save_text(email: str, subject: str, body: str):
    e, subject, body = email.lower(), clean(subject), clean(body)
    s = store.get(e)
    if s and s["status"] in EDITABLE:
        store.update(e, subject=subject, body=body + "\n\n" + SIGNATURE)
    elif not s:
        cfg.written_dir.mkdir(exist_ok=True)
        (cfg.written_dir / f"{contacts.slug(e)}.json").write_text(
            json.dumps({"subject": subject, "body": body}, indent=2, ensure_ascii=False), encoding="utf-8")


def save_contact(row: dict, old_email: str):
    e, old = row["email"], old_email.lower()
    contacts.upsert(row, old)
    s = store.get(old)
    if s:
        store.update(old, contact=row)
        if old != e and s["status"] in EDITABLE:
            store.rename(old, e)


def delete_contact(email: str):
    contacts.remove(email)
    s = store.get(email)
    if s and s["status"] in EDITABLE:
        store.delete(email)


def set_status(email: str, status: str):
    s = store.get(email)
    if s and s["status"] in EDITABLE and status in EDITABLE:
        store.update(email, status=status)


def set_stopped(email: str, stopped: bool):
    store.update(email, stopped=stopped)


def bulk(action: str, emails: list[str]):
    """Apply approve / unapprove / stop / resume / send (= approve) to many contacts."""
    for e in (x.lower() for x in emails):
        s = store.get(e)
        if not s:
            continue
        if action in ("approve", "send") and s["status"] == "drafted":
            store.update(e, status="approved")
        elif action == "unapprove" and s["status"] == "approved":
            store.update(e, status="drafted")
        elif action in ("stop", "resume") and s["status"] in ("approved", "sent"):
            store.update(e, stopped=action == "stop")


def ready_to_send(emails: list[str]) -> list[str]:
    return [e for e in (x.lower() for x in emails)
            if (s := store.get(e)) and s["status"] == "approved" and not s["stopped"]]


def redraft(email: str):
    s = store.get(email)
    if s and s["status"] in EDITABLE:
        store.delete(email)
