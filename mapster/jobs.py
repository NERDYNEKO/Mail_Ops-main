"""Runs one background job at a time and captures its log lines for the web panel."""
import logging
import threading

log = logging.getLogger("mapster")


class _Capture(logging.Handler):
    def __init__(self, jobs: "Jobs"):
        super().__init__()
        self.jobs = jobs

    def emit(self, record):
        if self.jobs.running:
            self.jobs.text += record.getMessage() + "\n"


class Jobs:
    def __init__(self):
        self.text = ""
        self.running = False
        self._lock = threading.Lock()
        log.addHandler(_Capture(self))
        log.setLevel(logging.INFO)

    def start(self, fn, *args, **kwargs) -> bool:
        """Run fn in a thread. Returns False if another job is already running."""
        with self._lock:
            if self.running:
                return False
            self.text, self.running = "", True

        def go():
            code = 0
            try:
                fn(*args, **kwargs)
            except SystemExit as ex:
                self.text += f"{ex}\n"
                code = 1
            except Exception as ex:
                log.exception("Job failed")
                self.text += f"Job failed: {ex}\n"
                code = 1
            self.text += f"\n[finished, exit {code}]\n"
            self.running = False

        threading.Thread(target=go, daemon=True).start()
        return True

    def state(self) -> dict:
        return {"text": self.text, "running": self.running}
