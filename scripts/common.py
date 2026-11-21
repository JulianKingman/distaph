"""Shared plumbing for Distaph scripts: library/config resolution, DB, drive
checks, and the library commit.

Scripts are standalone CLIs (specs/06-skill.md); this module holds only what
every one of them needs and nothing judgment-shaped.

The app (this repo) and the library (the user's data) are separate
(specs/08-library-and-launcher.md). The library is found by, in order:
$DISTAPH_LIBRARY, the path in ~/.config/distaph/library, then ~/Distaph.
Relative paths in distaph.toml resolve against the config file's folder.
"""

import os
import sqlite3
import sys
import tomllib
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = APP_ROOT  # back-compat alias
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
CONFIG_NAME = "distaph.toml"
LIBRARY_POINTER = Path("~/.config/distaph/library").expanduser()


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def library_root() -> Path:
    env = os.environ.get("DISTAPH_LIBRARY")
    if env:
        return Path(env).expanduser()
    if LIBRARY_POINTER.exists():
        return Path(LIBRARY_POINTER.read_text().strip()).expanduser()
    return Path("~/Distaph").expanduser()


def load_config(path: str | None = None) -> dict:
    p = Path(path).expanduser() if path else library_root() / CONFIG_NAME
    if not p.exists():
        die(f"config not found: {p} (run `distaph init` to create a library)")
    with open(p, "rb") as f:
        cfg = tomllib.load(f)
    cfg["_root"] = str(p.resolve().parent)
    return cfg


def resolve_path(cfg: dict, value: str) -> Path:
    """A distaph.toml path: absolute as given, else relative to the library."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else Path(cfg["_root"]) / p


def vault_path(cfg: dict) -> Path:
    return resolve_path(cfg, cfg["vault"]["path"])


def require_drive(cfg: dict) -> tuple[Path, Path]:
    """Fail loudly if the archive drive is unmounted (specs/07-operations.md).

    Returns (intake, archive) paths. archive/ is created if missing; intake/
    must already exist — its absence means the drive layout is wrong, not that
    there is nothing to do.
    """
    drive = Path(cfg["media"]["drive"])
    if not os.path.ismount(drive):
        die(f"archive drive not mounted: {drive}")
    intake = Path(cfg["media"]["intake"])
    archive = Path(cfg["media"]["archive"])
    if not intake.is_dir():
        die(f"intake directory missing on mounted drive: {intake}")
    archive.mkdir(parents=True, exist_ok=True)
    return intake, archive


def open_db(cfg: dict, db_override: str | None = None) -> sqlite3.Connection:
    path = Path(db_override) if db_override else resolve_path(cfg, cfg["db"]["path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, autocommit=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text())
    return conn


# Tables exported as text facts. Embeddings are excluded on purpose: they are
# derived from text + a model name and rebuild in minutes (`distaph embed`).
FACT_TABLES = {
    "clip": "id",
    "segment": "id",
    "keyframe": "id",
    "clip_project": "clip_id, project",
}


def export_facts(conn: sqlite3.Connection, out_dir: Path) -> dict:
    """Write each fact table as sorted JSON Lines: deterministic, diffable, and
    enough to rebuild the DB without re-running Whisper (specs/08)."""
    import json
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for table, order in FACT_TABLES.items():
        rows = conn.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
        with open(out_dir / f"{table}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(dict(r), sort_keys=True, ensure_ascii=False) + "\n")
        counts[table] = len(rows)
    return counts


def commit_library(cfg: dict, conn: sqlite3.Connection | None, message: str) -> str:
    """Export facts and commit the library, if the library is a git repo.

    Distaph is opinionated: your library should be under version control. It
    never pushes — where (and whether) the library goes is your call.
    """
    import subprocess
    root = Path(cfg["_root"])
    probe = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True)
    if probe.returncode != 0 or Path(probe.stdout.strip()).resolve() != root.resolve():
        return "skipped: library is not a git repository"
    if conn is not None:
        export_facts(conn, root / "facts")
    subprocess.run(["git", "-C", str(root), "add", "-A", "."], capture_output=True)
    c = subprocess.run(["git", "-C", str(root), "commit", "-m", message],
                       capture_output=True, text=True)
    return "committed" if c.returncode == 0 else "nothing to commit"
