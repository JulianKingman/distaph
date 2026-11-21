"""Tests for scripts/caption.

Hermetic: synthetic clips + a stub mlx_vlm on PYTHONPATH. Stub frame captions
embed the keyframe time, so time->caption alignment is checkable. Real VLM
quality is the bake-off's job, not these tests'.

Run:  uv run --python 3.14 --with pytest pytest tests/
"""

import hashlib
import json
import os
import subprocess

from conftest import STUB_VLM, ingest_pair, make_clip, rows
from conftest import run_script as run


def make_cut_clip(path):
    """9s clip with hard cuts at 3s and 6s (red|blue|green) — scene-detect bait."""
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "color=red:d=3:s=320x240:r=30",
         "-f", "lavfi", "-i", "color=blue:d=3:s=320x240:r=30",
         "-f", "lavfi", "-i", "color=green:d=3:s=320x240:r=30",
         "-filter_complex", "[0][1][2]concat=n=3:v=1:a=0",
         "-c:v", "libx264", "-preset", "ultrafast", str(path)],
        check=True, capture_output=True)


def test_interval_fallback_and_summary(env):
    ingest_pair(env)
    report = run("caption", env)

    assert report["model"] == STUB_VLM
    assert len(report["captioned"]) == 2  # BOTH angles: visuals differ
    assert all(c["method"] == "interval" for c in report["captioned"])

    clip = rows(env, "SELECT * FROM clip WHERE is_canonical_audio = 1")[0]
    kfs = rows(env, f"SELECT * FROM keyframe WHERE clip_id = '{clip['id']}' "
                    "ORDER BY t")
    # 3s clip: interval grid is empty, falls back to the midpoint frame
    assert len(kfs) == 1 and abs(kfs[0]["t"] - clip["duration_s"] / 2) < 0.1
    assert kfs[0]["id"] == f"kf_{clip['id'].removeprefix('clip_')}_0000"
    assert kfs[0]["model"] == STUB_VLM
    assert kfs[0]["caption"].startswith("Stub caption of frame")

    assert clip["visual_summary"] == "A stub visual summary of the whole clip."
    expected = hashlib.sha256(
        "\n".join(k["caption"] for k in kfs).encode()).hexdigest()
    assert clip["visual_summary_input_hash"] == expected


def test_scene_detect_path(env):
    make_cut_clip(env.intake / "cutty.mov")
    ingest = run("ingest", env)
    assert len(ingest["ingested"]) == 1
    report = run("caption", env)

    c = report["captioned"][0]
    assert c["method"] == "scene" and c["keyframes"] == 2
    ts = [k["t"] for k in rows(env, "SELECT t FROM keyframe ORDER BY t")]
    assert abs(ts[0] - 3.0) < 0.5 and abs(ts[1] - 6.0) < 0.5


def test_rerun_skips_captioned_and_explicit_recaption_replaces(env):
    ingest_pair(env)
    run("caption", env)
    assert run("caption", env)["captioned"] == []  # no-arg run: only uncaptioned

    clip_id = rows(env, "SELECT id FROM clip LIMIT 1")[0]["id"]
    run("caption", env, clip_id)
    kfs = rows(env, f"SELECT id FROM keyframe WHERE clip_id = '{clip_id}'")
    assert len(kfs) == 1  # replaced, not accumulated


def test_junk_frame_retries_at_nudged_time(env):
    make_clip(env.intake / "long.mov", duration=8, freq=440,
              creation_time="2026-01-05T10:00:00.000000Z")
    run("ingest", env)
    # grid for an 8s clip is [5.0]; the VLM "collapses" on that frame, so the
    # nudged 7.0 frame is used instead
    report = run("caption", env, env_extra={"STUB_VLM_JUNK_STEMS": "5.0"})
    c = report["captioned"][0]
    assert c["keyframes"] == 1 and c["skipped_frames"] == []
    kf = rows(env, "SELECT * FROM keyframe")[0]
    assert kf["t"] == 7.0 and "frame 7.0" in kf["caption"]


def test_all_black_clip_errors_without_burning_vlm(env):
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", "color=black:d=8:s=320x240:r=30",
         "-c:v", "libx264", "-preset", "ultrafast",
         str(env.intake / "black.mov")], check=True, capture_output=True)
    run("ingest", env)
    r = run("caption", env, expect_ok=False)
    assert r.returncode == 1
    report = json.loads(r.stdout)
    assert "no frame produced a caption" in report["errors"][0]["error"]
    assert "near-black" in report["errors"][0]["error"]
    assert rows(env, "SELECT * FROM keyframe") == []


def test_unset_model_dies(env):
    ingest_pair(env)
    env.cfg.write_text(env.cfg.read_text().replace(f'vlm = "{STUB_VLM}"',
                                                   'vlm = "TBD"'))
    r = run("caption", env, expect_ok=False)
    assert r.returncode == 1 and "bake-off" in r.stderr


def test_missing_media_reports_error(env):
    ingest_pair(env)
    victim = rows(env, "SELECT path FROM clip WHERE is_canonical_audio = 1")[0]
    os.remove(victim["path"])
    r = run("caption", env, expect_ok=False)
    assert r.returncode == 1
