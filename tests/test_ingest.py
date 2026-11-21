"""Tests for scripts/ingest.

Fixtures are tiny synthetic clips generated with ffmpeg (test pattern + tone,
distinct audio frequency per clip so content hashes differ), with controlled
creation_time metadata. No real footage, no real drive: the config's `drive`
points at "/" (always a mount) and intake/archive live in pytest tmp dirs.

Run:  uv run --python 3.14 --with pytest pytest tests/
(scripts need Python >= 3.12: tomllib + sqlite3 autocommit)
"""

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import make_clip

INGEST = Path(__file__).resolve().parent.parent / "scripts" / "ingest"

PAIR_TS = "2026-01-01T12:00:00.000000Z"


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """Named base clips, generated once and copied into per-test intakes."""
    d = tmp_path_factory.mktemp("base-clips")
    specs = {
        "pairA":   dict(duration=3, freq=440, creation_time=PAIR_TS),
        "pairB":   dict(duration=3, freq=445, creation_time=PAIR_TS),
        "dup_dur": dict(duration=3, freq=500, creation_time="2026-02-02T08:00:00.000000Z"),
        "ts_dup":  dict(duration=8, freq=550, creation_time=PAIR_TS),
        "solo":    dict(duration=8, freq=600, creation_time="2026-03-03T09:00:00.000000Z"),
        "undated": dict(duration=5, freq=660),
    }
    clips = {}
    for name, spec in specs.items():
        clips[name] = d / f"{name}.mov"
        make_clip(clips[name], **spec)
    return clips


@pytest.fixture
def env(tmp_path, base):
    """Isolated intake/archive/db/config. Call e.stage() to drop fixtures in."""
    intake, archive = tmp_path / "intake", tmp_path / "archive"
    intake.mkdir(), archive.mkdir()
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f'[media]\ndrive = "/"\nintake = "{intake}"\narchive = "{archive}"\n'
        f'\n[db]\npath = "unused.sqlite"\n\n[vault]\npath = "vault"\n')

    def stage(**name_to_key):
        for dest_name, key in name_to_key.items():
            shutil.copy(base[key], intake / dest_name)

    return SimpleNamespace(intake=intake, archive=archive, cfg=cfg,
                           db=tmp_path / "db.sqlite", stage=stage)


def run_ingest(e, *extra, expect_ok=True):
    r = subprocess.run(
        [sys.executable, str(INGEST), "--config", str(e.cfg),
         "--db", str(e.db), "--json", *extra],
        capture_output=True, text=True)
    if expect_ok:
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)
    return r


def rows(e, sql="SELECT * FROM clip"):
    conn = sqlite3.connect(e.db)
    conn.row_factory = sqlite3.Row
    return [dict(r) for r in conn.execute(sql)]


def test_basic_ingest_moves_and_records(env):
    env.stage(**{"solo.mov": "solo"})
    report = run_ingest(env)

    assert len(report["ingested"]) == 1
    r = rows(env)[0]
    assert r["source_name"] == "solo.mov"
    assert r["capture_date"] == "2026-03-03T09:00:00+00:00"
    assert r["capture_date_source"] == "embedded"
    assert r["codec"] == "h264" and r["width"] == 320 and r["fps"] == 30.0
    assert 7.5 < r["duration_s"] < 8.5

    # moved into <hash-prefix>/<hash>.<ext>, intake emptied
    archived = Path(r["path"])
    assert archived.exists() and not any(env.intake.iterdir())
    h = hashlib.sha256(archived.read_bytes()).hexdigest()
    assert r["content_hash"] == h
    assert archived == env.archive / h[:2] / f"{h}.mov"
    assert r["id"] == f"clip_{h[:12]}"


def test_take_group_pairing_same_run(env):
    env.stage(**{"01012026_120000_A.mov": "pairA", "01012026_120000_B.mov": "pairB"})
    report = run_ingest(env)

    assert list(report["take_groups"]) == ["01012026_120000"]
    by_name = {r["source_name"]: r for r in rows(env)}
    assert by_name["01012026_120000_A.mov"]["is_canonical_audio"] == 1
    assert by_name["01012026_120000_B.mov"]["is_canonical_audio"] == 0
    assert {r["take_group"] for r in by_name.values()} == {"01012026_120000"}
    # same duration + same capture ts, but siblings — never dupe-flagged
    assert report["possible_dupes"] == []


def test_take_group_pairing_across_runs(env):
    env.stage(**{"01012026_120000_A.mov": "pairA"})
    first = run_ingest(env)
    assert first["take_groups"] == {}

    env.stage(**{"01012026_120000_B.mov": "pairB"})
    second = run_ingest(env)
    assert "01012026_120000" in second["take_groups"]
    by_name = {r["source_name"]: r for r in rows(env)}
    assert by_name["01012026_120000_A.mov"]["is_canonical_audio"] == 1
    assert by_name["01012026_120000_B.mov"]["is_canonical_audio"] == 0
    assert {r["take_group"] for r in by_name.values()} == {"01012026_120000"}


def test_lone_b_stays_canonical(env):
    env.stage(**{"01012026_120000_B.mov": "pairB"})
    run_ingest(env)
    r = rows(env)[0]
    assert r["is_canonical_audio"] == 1 and r["take_group"] is None


def test_idempotent_rerun(env):
    env.stage(**{"solo.mov": "solo"})
    run_ingest(env)
    again = run_ingest(env)
    assert again["ingested"] == [] and len(rows(env)) == 1


def test_exact_dupe_held_in_intake(env):
    env.stage(**{"solo.mov": "solo"})
    run_ingest(env)
    env.stage(**{"renamed.mov": "solo"})  # same bytes, new name
    report = run_ingest(env)

    assert report["ingested"] == [] and len(report["exact_dupes"]) == 1
    assert (env.intake / "renamed.mov").exists()  # held for a human call
    assert len(rows(env)) == 1


def test_duration_dupe_flagged(env):
    env.stage(**{"01012026_120000_A.mov": "pairA", "dup_dur.mov": "dup_dur"})
    report = run_ingest(env)
    flags = [d for d in report["possible_dupes"] if d["file"] == "dup_dur.mov"]
    assert flags and all(f["reason"] == "duration" for f in flags)


def test_capture_timestamp_dupe_flagged(env):
    env.stage(**{"01012026_120000_A.mov": "pairA"})
    run_ingest(env)
    env.stage(**{"ts_dup.mov": "ts_dup"})  # same recording ts, 8s vs 3s
    report = run_ingest(env)
    flags = [d for d in report["possible_dupes"] if d["file"] == "ts_dup.mov"]
    assert flags and all(f["reason"] == "capture-timestamp" for f in flags)


def test_undated_flagged(env):
    env.stage(**{"undated.mov": "undated"})
    report = run_ingest(env)
    assert len(report["undated"]) == 1
    r = rows(env)[0]
    assert r["capture_date"] is None and r["capture_date_source"] is None


def test_dry_run_has_no_side_effects(env):
    env.stage(**{"solo.mov": "solo"})
    report = run_ingest(env, "--dry-run")
    assert len(report["ingested"]) == 1
    assert (env.intake / "solo.mov").exists()
    assert not any(env.archive.iterdir()) and rows(env) == []


def test_unmounted_drive_fails_loudly(env, tmp_path):
    env.cfg.write_text(env.cfg.read_text().replace('drive = "/"',
                       f'drive = "{tmp_path / "not-a-mount"}"'))
    r = run_ingest(env, expect_ok=False)
    assert r.returncode == 1 and "not mounted" in r.stderr


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0,
                    reason="root ignores directory permissions")
def test_failed_move_rolls_back(env, base):
    env.stage(**{"solo.mov": "solo"})
    h = hashlib.sha256(base["solo"].read_bytes()).hexdigest()
    blocked = env.archive / h[:2]
    blocked.mkdir()
    blocked.chmod(0o555)  # rename into it will fail after the row insert
    try:
        r = run_ingest(env, expect_ok=False)
        assert r.returncode == 1 and "move failed" in r.stderr
        assert (env.intake / "solo.mov").exists()   # intake stays truthful
        assert rows(env) == []                      # row rolled back
        assert not any(blocked.iterdir())
    finally:
        blocked.chmod(0o755)
