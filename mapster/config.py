"""All settings in one place, read once from the environment (.env)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class Config:
    gmail_user: str = os.getenv("GMAIL_USER", "mapster.officials@gmail.com")
    gmail_password: str = os.getenv("GMAIL_APP_PASSWORD", "")
    test_email: str = os.getenv("TEST_EMAIL", "")
    daily_cap: int = _int("DAILY_CAP", 25)
    delay: tuple = (_int("DELAY_MIN_SEC", 90), _int("DELAY_MAX_SEC", 240))
    followup_gap_days: float = float(os.getenv("FOLLOWUP_GAP_DAYS", "2"))
    followup_max: int = _int("FOLLOWUP_MAX", 10)  # safety net, replies stop it sooner
    send_hours: tuple = (_int("SEND_START_HOUR", 9), _int("SEND_END_HOUR", 19))
    model: str = os.getenv("WRITER_MODEL", "claude-sonnet-5-5")
    from_name: str = "MAPSTER"
    port: int = _int("PORT", 8765)
    autopilot_every_sec: int = 30 * 60

    root: Path = ROOT
    db_path: Path = ROOT / "data" / "mapster.db"
    contacts_csv: Path = ROOT / "contacts.csv"
    followup_templates: Path = ROOT / "followup_templates.json"
    written_dir: Path = ROOT / "written"
    out_dir: Path = ROOT / "out"
    assets_dir: Path = ROOT / "assets"
    static_dir: Path = ROOT / "mapster" / "static"

    @property
    def deck(self) -> Path:
        return self.assets_dir / "Mapster_PitchDeck.pdf"


cfg = Config()
DATE_FMT = "%Y-%m-%d %H:%M"
