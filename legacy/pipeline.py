"""Mapster outreach pipeline.

  python pipeline.py draft [--only a@x.com]   write emails for new contacts
  python pipeline.py approve --all            approve drafts (or list emails)
  python pipeline.py run [--dry] [--force] [--only a@x.com]
  python pipeline.py test a@x.com             send that email to TEST_EMAIL only
  python pipeline.py status
"""
import argparse
import csv
import imaplib
import json
import mimetypes
import os
import random
import re
import smtplib
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import make_msgid, formatdate

from dotenv import load_dotenv

load_dotenv()
GMAIL = os.getenv("GMAIL_USER", "mapster.officials@gmail.com")
APP_PW = os.getenv("GMAIL_APP_PASSWORD", "")
TEST_EMAIL = os.getenv("TEST_EMAIL", "")
DAILY_CAP = int(os.getenv("DAILY_CAP", "25"))
DELAY = (int(os.getenv("DELAY_MIN_SEC", "90")), int(os.getenv("DELAY_MAX_SEC", "240")))
FOLLOWUP_GAP_DAYS = float(os.getenv("FOLLOWUP_GAP_DAYS", "2"))
FOLLOWUP_MAX = int(os.getenv("FOLLOWUP_MAX", "10"))  # safety net, replies stop it sooner
SEND_HOURS = (int(os.getenv("SEND_START_HOUR", "9")), int(os.getenv("SEND_END_HOUR", "19")))
FROM_NAME = "MAPSTER"
STATE, CONTACTS = "state.json", "contacts.csv"
FMT = "%Y-%m-%d %H:%M"
DECK = "assets/Mapster_PitchDeck.pdf"


def load_state():
    return json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}


def save_state(s):
    json.dump(s, open(STATE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def load_contacts():
    if not os.path.exists(CONTACTS):
        return []
    with open(CONTACTS, newline="", encoding="utf-8-sig") as f:
        rows = [{k.strip().lower(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    for r in rows:
        r["category"] = r.get("category") or "client"
    return [r for r in rows if r.get("email")]


def slug(e):
    return re.sub(r"[^a-z0-9]+", "_", e.lower())


def attachment_for(s):
    """(path, filename). Clients get the proposal with their name on the cover, network gets the deck."""
    c = s["contact"]
    if c.get("category") == "network":
        return DECK, "Mapster_Pitch_Deck.pdf"
    from pdfgen import make_proposal
    os.makedirs("out", exist_ok=True)
    name = c.get("cover_name") or c.get("event") or c.get("org") or c.get("name")
    return make_proposal(name, f"out/Mapster_Proposal_{slug(c['email'])}.pdf"), "Mapster_Pilot_Proposal.pdf"


def shown_status(s):
    return "stopped" if s.get("stopped") and s["status"] in ("approved", "sent") else s["status"]


# ---------- draft ----------
def cmd_draft(args):
    from writer import write_first, SIGNATURE, clean
    state = load_state()
    for c in load_contacts():
        e = c["email"].lower()
        if e in state or (args.only and e not in [x.lower() for x in args.only]):
            continue
        pre = f"written/{slug(e)}.json"
        try:
            if os.path.exists(pre):
                w = json.load(open(pre, encoding="utf-8"))
                mail = {"subject": clean(w["subject"]), "body": clean(w["body"])}
            else:
                print("Writing email for", e, "...", flush=True)
                mail = write_first(c)
        except Exception as ex:
            print("FAILED for", e, ":", ex)
            continue
        state[e] = {"contact": c, "status": "drafted", "subject": mail["subject"],
                    "body": mail["body"] + "\n\n" + SIGNATURE, "sent": [], "message_ids": [],
                    "followups": 0, "stopped": False}
        save_state(state)
        print("Drafted", e)
    print("Done.")


def cmd_approve(args):
    state = load_state()
    for e, s in state.items():
        if s["status"] == "drafted" and (args.all or e in [x.lower() for x in args.emails]):
            s["status"] = "approved"
            print("Approved", e)
    save_state(state)


# ---------- mail ----------
def build(to, subject, body, attach=None, in_reply_to=None, refs=None):
    m = EmailMessage()
    m["From"] = f"{FROM_NAME} <{GMAIL}>"
    m["To"] = to
    m["Subject"] = subject
    m["Date"] = formatdate(localtime=True)
    m["Message-ID"] = make_msgid(domain="gmail.com")
    if in_reply_to:
        m["In-Reply-To"] = in_reply_to
        m["References"] = " ".join(refs or [in_reply_to])
    m.set_content(body)
    if attach:
        path, fname = attach
        main, sub = (mimetypes.guess_type(path)[0] or "application/pdf").split("/")
        with open(path, "rb") as f:
            m.add_attachment(f.read(), maintype=main, subtype=sub, filename=fname)
    return m


def smtp_send(msgs, delay=True):
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(GMAIL, APP_PW)
        for i, (e, m, done) in enumerate(msgs):
            srv.send_message(m)
            done(m["Message-ID"])
            print("Sent to", e, flush=True)
            if delay and i < len(msgs) - 1:
                time.sleep(random.randint(*DELAY))


def check_replies(state):
    """Mark contacts who replied or bounced so follow ups stop."""
    if not APP_PW:
        return
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(GMAIL, APP_PW)
        imap.select("INBOX")
        since = (datetime.now() - timedelta(days=60)).strftime("%d-%b-%Y")
        _, data = imap.search(None, f"(SINCE {since})")
        for num in data[0].split():
            _, d = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)] BODY.PEEK[TEXT]<0.3000>)")
            raw = b" ".join(p[1] for p in d if isinstance(p, tuple)).decode("utf-8", "ignore").lower()
            for e, s in state.items():
                if s["status"] != "sent" or e not in raw:
                    continue
                head = raw[:600]
                if "mailer-daemon" in head or "delivery status" in head or "undeliverable" in head:
                    s["status"] = "bounced"
                elif e in head:
                    s["status"] = "replied"
                else:
                    continue
                print(f"{e}: {s['status']}")
        imap.logout()
    except Exception as ex:
        print("Reply check failed (continuing):", ex)


def cmd_test(args):
    s = load_state().get(args.email.lower())
    if not s:
        raise SystemExit("No draft for that email.")
    if not (TEST_EMAIL and APP_PW):
        raise SystemExit("Set TEST_EMAIL and GMAIL_APP_PASSWORD in .env first.")
    smtp_send([(TEST_EMAIL, build(TEST_EMAIL, "[TEST] " + s["subject"], s["body"], attachment_for(s)),
                lambda mid: None)], delay=False)


def in_window():
    return SEND_HOURS[0] <= datetime.now().hour < SEND_HOURS[1]


def cmd_run(args):
    from writer import followup_text, SIGNATURE
    only = {x.lower() for x in (args.only or [])}
    if not (args.dry or args.force or only) and not in_window():
        print(f"Outside sending hours ({SEND_HOURS[0]}:00 to {SEND_HOURS[1]}:00). Nothing sent.")
        return
    state = load_state()
    check_replies(state)
    save_state(state)
    today = datetime.now().strftime("%Y-%m-%d")
    budget = max(0, DAILY_CAP - sum(1 for s in state.values() for t in s["sent"] if t[:10] == today))
    queue = []

    for e, s in state.items():
        if len(queue) >= budget:
            break
        if only and e not in only:
            continue
        if s.get("stopped"):
            continue
        if s["status"] == "approved":
            if args.dry:
                print(f"[dry] first email to {e}: {s['subject']}"); continue
            m = build(e, s["subject"], s["body"], attachment_for(s))

            def done(mid, s=s):
                s["status"] = "sent"; s["sent"].append(datetime.now().strftime(FMT)); s["message_ids"].append(mid)
                save_state(state)
            queue.append((e, m, done))
        elif s["status"] == "sent" and s["followups"] < FOLLOWUP_MAX:
            if datetime.now() - datetime.strptime(s["sent"][-1], FMT) < timedelta(days=FOLLOWUP_GAP_DAYS):
                continue
            n = s["followups"] + 1
            if args.dry:
                print(f"[dry] follow up {n} due for {e}"); continue
            body = followup_text(s["contact"], n) + "\n\n" + SIGNATURE
            subj = s["subject"] if s["subject"].lower().startswith("re:") else "Re: " + s["subject"]
            m = build(e, subj, body, None, s["message_ids"][0], s["message_ids"][:1])

            def done(mid, s=s):
                s["followups"] += 1; s["sent"].append(datetime.now().strftime(FMT)); s["message_ids"].append(mid)
                save_state(state)
            queue.append((e, m, done))

    if args.dry or not queue:
        print("Nothing to send." if not queue else "")
        return
    if not APP_PW:
        raise SystemExit("Set GMAIL_APP_PASSWORD in .env first.")
    print(f"Sending {len(queue)} email(s)...", flush=True)
    smtp_send(queue, delay=len(queue) > 1)
    print("Done.")


def cmd_status(args):
    state = load_state()
    counts = {}
    for e, s in state.items():
        st = shown_status(s)
        counts[st] = counts.get(st, 0) + 1
        print(f"{st:9} follow ups {s['followups']}  {e}")
    print(counts)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft"); d.add_argument("--only", nargs="+")
    a = sub.add_parser("approve"); a.add_argument("emails", nargs="*"); a.add_argument("--all", action="store_true")
    r = sub.add_parser("run"); r.add_argument("--dry", action="store_true"); r.add_argument("--force", action="store_true"); r.add_argument("--only", nargs="+")
    t = sub.add_parser("test"); t.add_argument("email")
    sub.add_parser("status")
    args = p.parse_args()
    {"draft": cmd_draft, "approve": cmd_approve, "run": cmd_run, "test": cmd_test, "status": cmd_status}[args.cmd](args)
