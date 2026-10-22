"""Local control panel for the Mapster pipeline.  Run: python ui.py  then open http://localhost:8765"""
import csv
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse, parse_qs

import pipeline as pl
import writer
from writer import SIGNATURE, clean

PORT = 8765
FIELDS = ["name", "email", "category", "org", "event", "cover_name", "website", "about"]
LOG = {"text": "", "running": False}
SETTINGS = "settings.json"
AUTOPILOT_EVERY = 30 * 60


def settings():
    return json.load(open(SETTINGS)) if os.path.exists(SETTINGS) else {"autopilot": False}


def read_contacts():
    return pl.load_contacts()


def write_contacts(rows):
    with open(pl.CONTACTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def strip_sig(body):
    return body[:-len(SIGNATURE)].rstrip() if body.endswith(SIGNATURE) else body


def items():
    state, out = pl.load_state(), []
    for c in read_contacts():
        e = c["email"].lower()
        s = state.get(e)
        wf = f"written/{pl.slug(e)}.json"
        w = json.load(open(wf, encoding="utf-8")) if os.path.exists(wf) else {}
        if s:
            subject, body = s["subject"], strip_sig(s["body"])
        else:
            subject, body = w.get("subject", ""), w.get("body", "")
        out.append({"contact": c, "email": e, "category": c["category"],
                    "status": pl.shown_status(s) if s else ("written" if w else "no draft"),
                    "has_state": bool(s), "stopped": bool(s and s.get("stopped")),
                    "subject": subject, "body": body, "sent": s["sent"] if s else [],
                    "followups_sent": s["followups"] if s else 0, "next_due": next_due(s)})
    return out


def next_due(s):
    if not s or s["status"] != "sent" or s.get("stopped") or s["followups"] >= pl.FOLLOWUP_MAX:
        return None
    last = datetime.strptime(s["sent"][-1], pl.FMT)
    return (last + timedelta(days=pl.FOLLOWUP_GAP_DAYS)).isoformat()


def run_bg(args):
    if LOG["running"]:
        return False
    LOG.update(text="", running=True)

    def go():
        p = subprocess.Popen([sys.executable, "-u", "pipeline.py"] + args, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            LOG["text"] += line
        p.wait()
        LOG["text"] += f"\n[finished, exit {p.returncode}]\n"
        LOG["running"] = False
    threading.Thread(target=go, daemon=True).start()
    return True


def autopilot_loop():
    last = 0
    while True:
        time.sleep(30)
        if settings().get("autopilot") and time.time() - last >= AUTOPILOT_EVERY and not LOG["running"]:
            last = time.time()
            run_bg(["run"])


def save_text(d):
    e = d["email"].lower()
    subject, body = clean(d["subject"]), clean(d["body"])
    state = pl.load_state()
    s = state.get(e)
    if s and s["status"] in ("drafted", "approved"):
        s.update(subject=subject, body=body + "\n\n" + SIGNATURE)
        pl.save_state(state)
    elif not s:
        json.dump({"subject": subject, "body": body}, open(f"written/{pl.slug(e)}.json", "w", encoding="utf-8"),
                  indent=2, ensure_ascii=False)


def preview(e):
    s = pl.load_state().get(e.lower())
    if not s:
        return {"error": "No draft yet. Click Generate email first."}
    c = s["contact"]
    _, fname = ("", "Mapster_Pitch_Deck.pdf") if c.get("category") == "network" else ("", "Mapster_Pilot_Proposal.pdf")
    subj = s["subject"] if s["subject"].lower().startswith("re:") else "Re: " + s["subject"]
    n = s["followups"] + 1
    return {"from": f"MAPSTER <{pl.GMAIL}>", "to": f"{c.get('name', '')} <{c['email']}>", "subject": s["subject"],
            "body": s["body"], "attachment": fname, "status": pl.shown_status(s),
            "followup_subject": subj, "followup_body": writer.followup_text(c, n) + "\n\n" + SIGNATURE,
            "followup_n": n, "cover": c.get("cover_name") or c.get("event") or c.get("org") or c.get("name"),
            "can_test": bool(pl.TEST_EMAIL and pl.APP_PW)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, data, ctype="application/json", code=200):
        b = data if isinstance(data, bytes) else (data if isinstance(data, str) else json.dumps(data)).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype != "application/pdf" else ""))
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            return self.send(page(), "text/html")
        if u.path == "/api/items":
            return self.send({"items": items(), "log": LOG, "cap": pl.DAILY_CAP, "has_pw": bool(pl.APP_PW),
                              "autopilot": settings().get("autopilot", False), "gap": pl.FOLLOWUP_GAP_DAYS,
                              "window": pl.SEND_HOURS})
        if u.path == "/api/preview":
            return self.send(preview(parse_qs(u.query)["email"][0]))
        if u.path == "/api/templates":
            return self.send(writer.load_pool())
        if u.path.startswith("/pdf/"):
            s = pl.load_state().get(unquote(u.path[5:]).lower())
            if s:
                return self.send(open(pl.attachment_for(s)[0], "rb").read(), "application/pdf")
        self.send({"error": "not found"}, code=404)

    def do_POST(self):
        d = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        p, msg = self.path, "ok"
        if p == "/api/save":
            save_text(d)
        elif p == "/api/contact":
            rows, e = read_contacts(), d["email"].lower()
            old = (d.get("old_email") or e).lower()
            rows = [r for r in rows if r["email"].lower() != old]
            row = {k: (d.get(k) or "").strip() for k in FIELDS} | {"email": e, "category": d.get("category") or "client"}
            rows.append(row)
            write_contacts(rows)
            st = pl.load_state()
            if old in st:
                st[old]["contact"] = row
                if old != e and st[old]["status"] in ("drafted", "approved"):
                    st[e] = st.pop(old); st[e]["contact"]["email"] = e
                pl.save_state(st)
        elif p == "/api/delete":
            e = d["email"].lower()
            write_contacts([r for r in read_contacts() if r["email"].lower() != e])
            st = pl.load_state()
            if st.get(e, {}).get("status") in ("drafted", "approved"):
                st.pop(e); pl.save_state(st)
        elif p == "/api/status":
            st = pl.load_state(); e = d["email"].lower()
            if e in st and st[e]["status"] in ("drafted", "approved") and d["status"] in ("drafted", "approved"):
                st[e]["status"] = d["status"]; pl.save_state(st)
        elif p == "/api/stop":
            st = pl.load_state(); e = d["email"].lower()
            if e in st:
                st[e]["stopped"] = bool(d["stopped"]); pl.save_state(st)
        elif p == "/api/bulk":
            st, em, act = pl.load_state(), [x.lower() for x in d["emails"]], d["action"]
            for e in em:
                s = st.get(e)
                if not s:
                    continue
                if act == "approve" and s["status"] == "drafted":
                    s["status"] = "approved"
                elif act == "unapprove" and s["status"] == "approved":
                    s["status"] = "drafted"
                elif act in ("stop", "resume") and s["status"] in ("approved", "sent"):
                    s["stopped"] = act == "stop"
                elif act == "send" and s["status"] == "drafted":
                    s["status"] = "approved"
            pl.save_state(st)
            if act == "generate":
                msg = "ok" if run_bg(["draft", "--only"] + em) else "busy"
            elif act == "send":
                ready = [e for e in em if st.get(e, {}).get("status") == "approved" and not st[e].get("stopped")]
                msg = ("ok" if run_bg(["run", "--force", "--only"] + ready) else "busy") if ready else "none"
        elif p == "/api/approve_all":
            st = pl.load_state()
            for s in st.values():
                if s["status"] == "drafted":
                    s["status"] = "approved"
            pl.save_state(st)
        elif p == "/api/redraft":
            st = pl.load_state(); e = d["email"].lower()
            if st.get(e, {}).get("status") in ("drafted", "approved"):
                st.pop(e); pl.save_state(st)
        elif p == "/api/gen":
            msg = "ok" if run_bg(["draft"] + (["--only", d["email"]] if d.get("email") else [])) else "busy"
        elif p == "/api/send_one":
            st = pl.load_state(); e = d["email"].lower()
            if st.get(e, {}).get("status") == "drafted":
                st[e]["status"] = "approved"; pl.save_state(st)
            msg = "ok" if run_bg(["run", "--force", "--only", e]) else "busy"
        elif p == "/api/test":
            msg = "ok" if run_bg(["test", d["email"]]) else "busy"
        elif p == "/api/run":
            msg = "ok" if run_bg(["run", "--dry"] if d.get("dry") else ["run", "--force"]) else "busy"
        elif p == "/api/templates":
            writer.save_pool({k: [clean(x) if False else x.strip() for x in v if x.strip()] for k, v in d.items()})
        elif p == "/api/autopilot":
            json.dump({"autopilot": bool(d["on"])}, open(SETTINGS, "w"))
        else:
            return self.send({"error": "unknown"}, code=404)
        self.send({"ok": msg == "ok", "msg": msg})


def page():
    return open("ui.html", encoding="utf-8").read()

if __name__ == "__main__":
    os.makedirs("written", exist_ok=True)
    os.makedirs("out", exist_ok=True)
    threading.Thread(target=autopilot_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print(f"Mapster control panel: http://localhost:{PORT}  (Ctrl+C to stop)")
    webbrowser.open(f"http://localhost:{PORT}")
    srv.serve_forever()
