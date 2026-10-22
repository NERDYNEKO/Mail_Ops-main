"""SMTP sending and IMAP reply/bounce detection for Gmail."""
import imaplib
import logging
import mimetypes
import random
import smtplib
import time
from datetime import datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Callable

from . import store
from .config import cfg

log = logging.getLogger("mapster")


def build(to: str, subject: str, body: str, attach: tuple[Path, str] | None = None,
          in_reply_to: str | None = None, refs: list[str] | None = None) -> EmailMessage:
    m = EmailMessage()
    m["From"] = f"{cfg.from_name} <{cfg.gmail_user}>"
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
        main, sub = (mimetypes.guess_type(str(path))[0] or "application/pdf").split("/")
        m.add_attachment(Path(path).read_bytes(), maintype=main, subtype=sub, filename=fname)
    return m


def send(batch: list[tuple[str, EmailMessage, Callable[[str], None]]], delay: bool = True):
    """Send (recipient, message, on_sent) tuples over one SMTP session, with a random pause between."""
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as srv:
        srv.login(cfg.gmail_user, cfg.gmail_password)
        for i, (to, msg, on_sent) in enumerate(batch):
            srv.send_message(msg)
            on_sent(msg["Message-ID"])
            log.info("Sent to %s", to)
            if delay and i < len(batch) - 1:
                time.sleep(random.randint(*cfg.delay))


def check_replies():
    """Mark contacts who replied or bounced so follow ups stop."""
    if not cfg.gmail_password:
        return
    sent = {e: s for e, s in store.all_items().items() if s["status"] == "sent"}
    if not sent:
        return
    try:
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        imap.login(cfg.gmail_user, cfg.gmail_password)
        imap.select("INBOX")
        since = (datetime.now() - timedelta(days=60)).strftime("%d-%b-%Y")
        _, data = imap.search(None, f"(SINCE {since})")
        for num in data[0].split():
            _, d = imap.fetch(num, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)] BODY.PEEK[TEXT]<0.3000>)")
            raw = b" ".join(p[1] for p in d if isinstance(p, tuple)).decode("utf-8", "ignore").lower()
            head = raw[:600]
            for e, s in list(sent.items()):
                if e not in raw:
                    continue
                if any(k in head for k in ("mailer-daemon", "delivery status", "undeliverable")):
                    status = "bounced"
                elif e in head:
                    status = "replied"
                else:
                    continue
                store.update(e, status=status)
                del sent[e]
                log.info("%s: %s", e, status)
        imap.logout()
    except Exception as ex:
        log.warning("Reply check failed (continuing): %s", ex)
