"""Local control panel API (FastAPI). Run with: python -m mapster ui"""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict

from . import contacts, followups, service, store
from .config import cfg
from .jobs import Jobs
from .text import clean

jobs = Jobs()


async def _autopilot():
    last = 0.0
    while True:
        await asyncio.sleep(30)
        if store.get_setting("autopilot", False) and time.time() - last >= cfg.autopilot_every_sec:
            if jobs.start(service.run):
                last = time.time()


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init()
    cfg.written_dir.mkdir(exist_ok=True)
    cfg.out_dir.mkdir(exist_ok=True)
    task = asyncio.create_task(_autopilot())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None)


class Email(BaseModel):
    email: str


class Gen(BaseModel):
    email: str | None = None


class Text(Email):
    subject: str
    body: str


class Status(Email):
    status: str


class Stop(Email):
    stopped: bool


class Bulk(BaseModel):
    action: str
    emails: list[str]


class Run(BaseModel):
    dry: bool = False


class Autopilot(BaseModel):
    on: bool


class Contact(BaseModel):
    model_config = ConfigDict(extra="ignore")
    email: str
    old_email: str | None = None
    name: str = ""
    category: str = "client"
    org: str = ""
    event: str = ""
    cover_name: str = ""
    website: str = ""
    about: str = ""


def reply(started: bool = True, msg: str | None = None):
    msg = msg or ("ok" if started else "busy")
    return {"ok": msg == "ok", "msg": msg}


# ---------- reads ----------
@app.get("/")
def index():
    return FileResponse(cfg.static_dir / "index.html")


@app.get("/api/items")
def get_items():
    return {"items": service.items(), "log": jobs.state(), "cap": cfg.daily_cap,
            "has_pw": bool(cfg.gmail_password), "autopilot": store.get_setting("autopilot", False),
            "gap": cfg.followup_gap_days, "window": cfg.send_hours}


@app.get("/api/preview")
def get_preview(email: str):
    return service.preview(email)


@app.get("/api/templates")
def get_templates():
    return followups.load_pool()


@app.get("/pdf/{email}")
def get_pdf(email: str):
    s = store.get(email)
    if not s:
        return JSONResponse({"error": "not found"}, status_code=404)
    path, _ = service.attachment_for(s)
    return Response(path.read_bytes(), media_type="application/pdf")


# ---------- edits ----------
@app.post("/api/save")
def save(d: Text):
    service.save_text(d.email, d.subject, d.body)
    return reply()


@app.post("/api/contact")
def save_contact(d: Contact):
    row = d.model_dump(exclude={"old_email"})
    row = {k: (v or "").strip() for k, v in row.items()} | {"email": d.email.lower(), "category": d.category or "client"}
    service.save_contact({k: row.get(k, "") for k in contacts.FIELDS}, d.old_email or d.email)
    return reply()


@app.post("/api/delete")
def delete(d: Email):
    service.delete_contact(d.email)
    return reply()


@app.post("/api/status")
def status(d: Status):
    service.set_status(d.email.lower(), d.status)
    return reply()


@app.post("/api/stop")
def stop(d: Stop):
    service.set_stopped(d.email.lower(), d.stopped)
    return reply()


@app.post("/api/redraft")
def redraft(d: Email):
    service.redraft(d.email.lower())
    return reply()


@app.post("/api/approve_all")
def approve_all():
    service.approve()
    return reply()


@app.post("/api/templates")
def save_templates(pool: dict[str, list[str]]):
    followups.save_pool({k: [x.strip() for x in v if x.strip()] for k, v in pool.items()})
    return reply()


@app.post("/api/autopilot")
def autopilot(d: Autopilot):
    store.set_setting("autopilot", d.on)
    return reply()


# ---------- background jobs ----------
@app.post("/api/bulk")
def bulk(d: Bulk):
    emails = [x.lower() for x in d.emails]
    service.bulk(d.action, emails)
    if d.action == "generate":
        return reply(jobs.start(service.draft, emails))
    if d.action == "send":
        ready = service.ready_to_send(emails)
        return reply(msg="none") if not ready else reply(jobs.start(service.run, force=True, only=ready))
    return reply()


@app.post("/api/gen")
def gen(d: Gen):
    return reply(jobs.start(service.draft, [d.email] if d.email else None))


@app.post("/api/send_one")
def send_one(d: Email):
    e = d.email.lower()
    service.bulk("approve", [e])
    return reply(jobs.start(service.run, force=True, only=[e]))


@app.post("/api/test")
def test(d: Email):
    return reply(jobs.start(service.send_test, d.email.lower()))


@app.post("/api/run")
def run(d: Run):
    return reply(jobs.start(service.run, dry=True) if d.dry else jobs.start(service.run, force=True))
