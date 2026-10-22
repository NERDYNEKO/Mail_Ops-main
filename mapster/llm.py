"""One function: complete(system, user). Uses the Anthropic API when a key is set,
otherwise the local `claude` CLI."""
import os
import shutil
import subprocess
from functools import lru_cache

from .config import cfg

try:
    import anthropic
except ImportError:
    anthropic = None


@lru_cache(maxsize=1)
def _client():
    return anthropic.Anthropic()


def complete(system: str, user: str) -> str:
    if os.getenv("ANTHROPIC_API_KEY") and anthropic:
        msg = _client().messages.create(model=cfg.model, max_tokens=1000, system=system,
                                        messages=[{"role": "user", "content": user}])
        return msg.content[0].text
    exe = shutil.which("claude")
    if not exe:
        raise RuntimeError("No ANTHROPIC_API_KEY and the `claude` CLI was not found.")
    r = subprocess.run([exe, "-p", "--output-format", "text"], input=system + "\n\n" + user,
                       capture_output=True, text=True, encoding="utf-8", timeout=240)
    if r.returncode != 0:
        raise RuntimeError("claude CLI failed: " + (r.stderr or r.stdout)[:300])
    return r.stdout
