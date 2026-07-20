"""Single source of truth for where runtime files live, so the app works both
from source (repo root) and as a frozen PyInstaller .exe.

Frozen build layout (next to Daily-HIS-Report.exe):
  - read-only assets (frontend/dist, config defaults) live inside the bundle
    (sys._MEIPASS);
  - writable data (config/*.json, backend/data/*.json, data/outputs/) lives
    next to the .exe so it PERSISTS across restarts and isn't wiped on the
    ephemeral temp extraction.
On first frozen launch the shipped config defaults are copied out of the
bundle into the writable config dir (only if not already present).
"""
import json
import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

# Read-only shipped assets (PyInstaller onefile extracts these to a temp dir
# that is wiped after each run -- never write here).
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))

# Writable root that survives across runs. Frozen: %APPDATA%\... (never the
# temp extraction, never Program Files). Source: repo root.
if FROZEN:
    ROOT = Path(os.environ.get("APPDATA", Path.home())) / "HospitalReportAutomation"
else:
    ROOT = Path(__file__).resolve().parent.parent

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "backend" / "data"
FRONTEND_DIST = BUNDLE_DIR / "dist"

SETTINGS_FILE = CONFIG_DIR / "settings.json"
DEFAULT_OUTPUT_DIR = Path.home() / "Documents" / "HospitalReportAutomation"


def build_output_path(report_date) -> Path:
    """The one place that decides where a Final Output workbook is written:
    <output_dir>/<Month YYYY>/Final Output - <dd-mm-yyyy>.xlsx. Re-running
    the same date overwrites that file rather than creating a duplicate."""
    month_dir = get_output_dir() / report_date.strftime("%B %Y")
    month_dir.mkdir(parents=True, exist_ok=True)
    return month_dir / f"Final Output - {report_date.strftime('%d-%m-%Y')}.xlsx"


def get_output_dir() -> Path:
    """Where generated workbooks are written. User-editable via
    set_output_dir(); defaults to the Documents folder."""
    try:
        raw = json.loads(SETTINGS_FILE.read_text()).get("output_dir")
    except (FileNotFoundError, ValueError):
        raw = None
    return Path(raw) if raw else DEFAULT_OUTPUT_DIR


def set_output_dir(path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    settings = {}
    if SETTINGS_FILE.exists():
        try:
            settings = json.loads(SETTINGS_FILE.read_text())
        except ValueError:
            settings = {}
    settings["output_dir"] = str(path)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2))
    return path

_SHIPPED_CONFIG = [
    "category_map.json",
    "daily_history.json",
    "learned_overrides.json",
    "final_output_template.xlsx",
]


def ensure_runtime_files() -> None:
    """Create writable dirs and seed shipped config defaults (frozen only)."""
    for d in (CONFIG_DIR, DATA_DIR, get_output_dir()):
        d.mkdir(parents=True, exist_ok=True)
    if FROZEN:
        for name in _SHIPPED_CONFIG:
            dest, src = CONFIG_DIR / name, BUNDLE_DIR / "config" / name
            if not dest.exists() and src.exists():
                shutil.copy2(src, dest)
