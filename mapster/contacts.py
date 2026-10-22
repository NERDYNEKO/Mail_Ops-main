import csv
import re

from .config import cfg

FIELDS = ["name", "email", "category", "org", "event", "cover_name", "website", "about"]


def slug(email: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", email.lower())


def load() -> list[dict]:
    if not cfg.contacts_csv.exists():
        return []
    with open(cfg.contacts_csv, newline="", encoding="utf-8-sig") as f:
        rows = [{k.strip().lower(): (v or "").strip() for k, v in r.items() if k} for r in csv.DictReader(f)]
    for r in rows:
        r["category"] = r.get("category") or "client"
    return [r for r in rows if r.get("email")]


def save(rows: list[dict]):
    with open(cfg.contacts_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in FIELDS} for r in rows)


def upsert(row: dict, old_email: str | None = None):
    old = (old_email or row["email"]).lower()
    rows = [r for r in load() if r["email"].lower() != old]
    save(rows + [row])


def remove(email: str):
    save([r for r in load() if r["email"].lower() != email.lower()])
