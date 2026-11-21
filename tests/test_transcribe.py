"""Tests for scripts/transcribe.

Hermetic: clips are synthetic (conftest.make_clip) and mlx_whisper is a stub
injected via PYTHONPATH (tests/stubs), so no model download or GPU. The real
whisper integration is exercised by the bake-off / first real run, not here.

Run:  uv run --python 3.14 --with pytest pytest tests/
"""

import json
import os

from conftest import STUB_WHISPER as MODEL
from conftest import ingest_pair, rows
from conftest import run_script as run


def test_transcribes_canonical_only_with_gen1_ids(env):
    ingest_pair(env)
    report = run("transcribe", env)

    assert report["model"] == MODEL
    assert len(report["transcribed"]) == 1  # _B is non-canonical, skipped
    t = report["transcribed"][0]
    assert t["gen"] == 1 and t["segments"] == 2  # blank third segment dropped

    segs = rows(env, "SELECT * FROM segment ORDER BY idx")
    clip = rows(env, "SELECT * FROM clip WHERE is_canonical_audio = 1")[0]
    hash_tail = clip["id"].removeprefix("clip_")
    assert [s["id"] for s in segs] == [f"seg_{hash_tail}_r1_0000",
                                       f"seg_{hash_tail}_r1_0001"]
    assert segs[0]["text"] == f"Hello from {MODEL}."
    assert segs[0]["t_in"] == 0.0 and segs[0]["t_out"] == 1.5
    words = json.loads(segs[1]["words_json"])
    assert words[0] == {"w": " Second", "t0": 1.5, "t1": 2.0}
    assert clip["transcribe_gen"] == 1 and clip["transcribed_at"]


def test_rerun_is_noop_without_explicit_ids(env):
    ingest_pair(env)
    run("transcribe", env)
    again = run("transcribe", env)
    assert again["transcribed"] == []  # already transcribed, not re-done


def test_explicit_retranscribe_bumps_gen_and_replaces(env):
    ingest_pair(env)
    run("transcribe", env)
    clip_id = rows(env, "SELECT id FROM clip WHERE is_canonical_audio = 1")[0]["id"]
    old_ids = {s["id"] for s in rows(env, "SELECT id FROM segment")}

    report = run("transcribe", env, clip_id)
    assert report["transcribed"][0]["gen"] == 2

    segs = rows(env, "SELECT * FROM segment ORDER BY idx")
    assert len(segs) == 2  # old generation destroyed, not accumulated
    assert all(s["gen"] == 2 and "_r2_" in s["id"] for s in segs)
    assert not old_ids & {s["id"] for s in segs}  # r1 IDs can never resolve again
    assert rows(env, "SELECT transcribe_gen FROM clip WHERE id = "
                f"'{clip_id}'")[0]["transcribe_gen"] == 2


def test_unknown_clip_id_dies(env):
    ingest_pair(env)
    r = run("transcribe", env, "clip_nope", expect_ok=False)
    assert r.returncode == 1 and "unknown clip id" in r.stderr


def test_unset_model_dies(env):
    env.cfg.write_text(env.cfg.read_text().replace(f'whisper = "{MODEL}"',
                                                   'whisper = "TBD"'))
    r = run("transcribe", env, expect_ok=False)
    assert r.returncode == 1 and "bake-off" in r.stderr


def test_missing_media_reports_error(env):
    ingest_pair(env)
    victim = rows(env, "SELECT path FROM clip WHERE is_canonical_audio = 1")[0]
    os.remove(victim["path"])
    r = run("transcribe", env, expect_ok=False)
    assert r.returncode == 1
    report = json.loads(r.stdout)
    assert "media missing" in report["errors"][0]["error"]
    assert rows(env, "SELECT * FROM segment") == []
