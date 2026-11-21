import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
STUBS = Path(__file__).resolve().parent / "stubs"
STUB_WHISPER = "stub-org/stub-whisper"
STUB_VLM = "stub-org/stub-vlm"
STUB_EMBEDDER = "stub-org/stub-embedder"


def make_clip(path, *, duration, freq, creation_time=None):
    """Tiny synthetic clip: test pattern + tone. Distinct freq => distinct hash."""
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=320x240:rate=30",
           "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={duration}",
           "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest"]
    if creation_time:
        cmd += ["-metadata", f"creation_time={creation_time}"]
    subprocess.run(cmd + [str(path)], check=True, capture_output=True)


@pytest.fixture
def env(tmp_path):
    """Isolated intake/archive/db/vault/config with stub model names configured."""
    intake, archive = tmp_path / "intake", tmp_path / "archive"
    vault = tmp_path / "vault"
    intake.mkdir(), archive.mkdir()
    (vault / "projects").mkdir(parents=True)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f'[media]\ndrive = "/"\nintake = "{intake}"\narchive = "{archive}"\n'
        f'\n[db]\npath = "unused.sqlite"\n\n[vault]\npath = "{vault}"\n'
        f'\n[models]\nwhisper = "{STUB_WHISPER}"\nvlm = "{STUB_VLM}"\n'
        f'embedder = "{STUB_EMBEDDER}"\n')
    return SimpleNamespace(intake=intake, archive=archive, vault=vault, cfg=cfg,
                           db=tmp_path / "db.sqlite")


def run_script(script, e, *extra, expect_ok=True, env_extra=None):
    """Invoke a scripts/ CLI with the stubs dir on PYTHONPATH (hermetic models).
    SYNC_CHILD_PYTHON keeps sync's child stages on this interpreter + stubs."""
    env_vars = dict(os.environ, PYTHONPATH=str(STUBS),
                    SYNC_CHILD_PYTHON=sys.executable, **(env_extra or {}))
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--config", str(e.cfg),
         "--db", str(e.db), "--json", *extra],
        capture_output=True, text=True, env=env_vars)
    if expect_ok:
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)
    return r


def rows(e, sql):
    conn = sqlite3.connect(e.db)
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql)]


def ingest_pair(e):
    make_clip(e.intake / "01012026_120000_A.mov", duration=3, freq=440,
              creation_time="2026-01-01T12:00:00.000000Z")
    make_clip(e.intake / "01012026_120000_B.mov", duration=3, freq=445,
              creation_time="2026-01-01T12:00:00.000000Z")
    return run_script("ingest", e)
