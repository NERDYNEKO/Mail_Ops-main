"""Command line entry point.

  python -m mapster ui                        open the control panel
  python -m mapster draft [--only a@x.com]    write emails for new contacts
  python -m mapster approve --all             approve drafts (or list emails)
  python -m mapster run [--dry] [--force] [--only a@x.com]
  python -m mapster test a@x.com              send that email to TEST_EMAIL only
  python -m mapster status
"""
import argparse
import logging
import threading
import webbrowser

from . import service, store
from .config import cfg


def main():
    p = argparse.ArgumentParser(prog="mapster")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ui")
    sub.add_parser("draft").add_argument("--only", nargs="+")
    a = sub.add_parser("approve")
    a.add_argument("emails", nargs="*")
    a.add_argument("--all", action="store_true")
    r = sub.add_parser("run")
    r.add_argument("--dry", action="store_true")
    r.add_argument("--force", action="store_true")
    r.add_argument("--only", nargs="+")
    sub.add_parser("test").add_argument("email")
    sub.add_parser("status")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    store.init()
    if args.cmd == "ui":
        import uvicorn
        url = f"http://localhost:{cfg.port}"
        print(f"Mapster control panel: {url}  (Ctrl+C to stop)")
        threading.Timer(1.0, webbrowser.open, [url]).start()
        uvicorn.run("mapster.api:app", host="127.0.0.1", port=cfg.port, log_level="warning")
    elif args.cmd == "draft":
        service.draft(args.only)
    elif args.cmd == "approve":
        service.approve(None if args.all else args.emails)
    elif args.cmd == "run":
        service.run(args.dry, args.force, args.only)
    elif args.cmd == "test":
        service.send_test(args.email.lower())
    elif args.cmd == "status":
        lines, counts = service.status_lines()
        print("\n".join(lines))
        print(counts)


if __name__ == "__main__":
    main()
