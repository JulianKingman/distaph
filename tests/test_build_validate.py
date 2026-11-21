"""Tests for scripts/build + scripts/validate.

Hermetic: stub whisper provides known segments. FCPXML output is parsed with
ElementTree and checked against the round-trip contract from spike/FINDINGS.md
(rational times, absolute file:// paths, offsets accumulating on the sequence
grid).

Run:  uv run --python 3.14 --with pytest pytest tests/
"""

import json
import sqlite3
import xml.etree.ElementTree as ET

from conftest import ingest_pair, rows
from conftest import run_script as run


def prepare(e):
    ingest_pair(e)
    run("transcribe", e)
    return [s["id"] for s in rows(e, "SELECT id FROM segment ORDER BY idx")]


def write_cut(e, seg_ids, name="test-cut"):
    cut = e.cfg.parent / "cut.json"
    cut.write_text(json.dumps({"name": name, "segments": seg_ids}))
    return str(cut)


def test_build_fcpxml_matches_spike_contract(env):
    seg_ids = prepare(env)
    out = env.cfg.parent / "out.fcpxml"
    r = run("build", env, write_cut(env, [seg_ids[1], seg_ids[0]]),
            "--fcpxml", str(out), "--pad", "0", expect_ok=False)
    assert r.returncode == 0, r.stderr

    root = ET.fromstring(out.read_text())
    assert root.tag == "fcpxml" and root.get("version") == "1.10"
    clips = root.findall(".//asset-clip")
    assert [c.get("name") for c in clips] == [seg_ids[1], seg_ids[0]]  # order kept
    # one shared asset (both segments live on the canonical clip), absolute URL
    assets = root.findall(".//asset")
    assert len(assets) == 1
    src = assets[0].find("media-rep").get("src")
    assert src.startswith("file:///") and not src.startswith("file:////")
    assert "/archive/" in src
    # times: 30fps synthetic → frame-grid rationals; offsets accumulate
    # stub segments: [1.5, 2.9] then [0.0, 1.5] → 42 + 45 frames at 30fps
    assert clips[0].get("offset") == "0/30s"
    assert clips[0].get("start") == "45/30s" and clips[0].get("duration") == "42/30s"
    assert clips[1].get("offset") == "42/30s"
    assert clips[1].get("duration") == "45/30s"
    seq = root.find(".//sequence")
    assert seq.get("duration") == "87/30s"


def test_build_refuses_unknown_id(env):
    seg_ids = prepare(env)
    out = env.cfg.parent / "out.fcpxml"
    r = run("build", env, write_cut(env, seg_ids + ["seg_fabricated_r1_0000"]),
            "--fcpxml", str(out), expect_ok=False)
    assert r.returncode == 1 and "hallucinated" in r.stderr
    assert not out.exists()


def test_build_txt_is_verbatim_transcript(env):
    seg_ids = prepare(env)
    out = env.cfg.parent / "script.txt"
    run("build", env, write_cut(env, seg_ids), "--txt", str(out),
        expect_ok=False)
    assert out.read_text() == ("Hello from stub-org/stub-whisper.\n"
                               "Second sentence here.\n")


def test_build_pip_connects_sibling_angle(env):
    seg_ids = prepare(env)
    cut = env.cfg.parent / "pip-cut.json"
    cut.write_text(json.dumps([{"id": seg_ids[0], "pip": True}]))
    out = env.cfg.parent / "pip.fcpxml"
    r = run("build", env, str(cut), "--fcpxml", str(out), "--pad", "0",
            expect_ok=False)
    assert r.returncode == 0, r.stderr

    root = ET.fromstring(out.read_text())
    assert len(root.findall(".//asset")) == 2  # A angle + B sibling
    primary = root.find(".//spine/asset-clip")
    child = primary.find("asset-clip")
    assert child.get("lane") == "1"
    assert child.get("ref") != primary.get("ref")
    assert child.get("offset") == primary.get("start")  # time-aligned takes
    assert child.get("duration") == primary.get("duration")
    xf = child.find("adjust-transform")
    assert xf is not None and xf.get("scale") == "0.34 0.34"
    # verbatim from a Resolve-authored export — the one placement known to
    # render on-screen; Resolve's units defeat canvas math (twice)
    assert xf.get("position") == "16.6667 31.25"


def test_padding_adds_breathing_room_but_not_across_adjacent_source(env):
    seg_ids = prepare(env)
    out = env.cfg.parent / "padded.fcpxml"
    # stub segments are source-adjacent ([0,1.5] then [1.5,2.9], same clip):
    # the shared boundary must NOT be padded (audio would repeat), while the
    # cut's outer edges get the breathing room.
    r = run("build", env, write_cut(env, seg_ids), "--fcpxml", str(out),
            expect_ok=False)
    assert r.returncode == 0, r.stderr
    clips = ET.fromstring(out.read_text()).findall(".//asset-clip")
    frames = [int(c.get("duration").split("/")[0]) for c in clips]
    assert frames[0] == 45   # [0,1.5]: t_in clamped at 0, boundary kept
    assert frames[1] > 42    # [1.5,2.9]: boundary kept, tail padded out


def test_build_pip_without_sibling_dies(env):
    from conftest import make_clip
    make_clip(env.intake / "solo.mov", duration=3, freq=550,
              creation_time="2026-01-02T10:00:00.000000Z")
    run("ingest", env)
    run("transcribe", env)
    solo_seg = rows(env, "SELECT s.id FROM segment s JOIN clip c ON c.id=s.clip_id "
                         "WHERE c.take_group IS NULL LIMIT 1")[0]["id"]
    cut = env.cfg.parent / "bad-pip.json"
    cut.write_text(json.dumps([{"id": solo_seg, "pip": True}]))
    r = run("build", env, str(cut), "--fcpxml",
            str(env.cfg.parent / "x.fcpxml"), expect_ok=False)
    assert r.returncode == 1 and "no take-group sibling" in r.stderr


def test_validate_clean_cut_ok(env):
    seg_ids = prepare(env)
    r = run("validate", env, "--cut", write_cut(env, seg_ids))
    assert r["ok"] and r["checked"] == 2
    assert r["missing"] == [] and r["bounds"] == [] and r["drift"] == []


def test_validate_missing_and_bounds(env):
    seg_ids = prepare(env)
    conn = sqlite3.connect(env.db)
    conn.execute("UPDATE segment SET t_out = 99.0 WHERE id = ?", (seg_ids[1],))
    conn.commit()
    r = run("validate", env, "--cut",
            write_cut(env, seg_ids + ["seg_dead_r1_0000"]), expect_ok=False)
    report = json.loads(r.stdout)
    assert r.returncode == 1 and not report["ok"]
    assert report["missing"] == ["seg_dead_r1_0000"]
    assert [b["id"] for b in report["bounds"]] == [seg_ids[1]]


def test_validate_narrative_echo_drift_warns_but_passes(env):
    seg_ids = prepare(env)
    nar = env.cfg.parent / "narrative.md"
    nar.write_text(f"""# thread
1. {seg_ids[0]}   <!-- Hello from stub-org/stub-whisper. -->
2. {seg_ids[1]}   <!-- something entirely different was said here, reworded -->
""")
    r = run("validate", env, "--narrative", str(nar))
    assert r["ok"] and r["checked"] == 2  # drift warns, never blocks
    assert [d["id"] for d in r["drift"]] == [seg_ids[1]]
    assert r["drift"][0]["similarity"] < 0.6


def test_validate_old_generation_fails_after_retranscribe(env):
    seg_ids = prepare(env)
    clip_id = rows(env, "SELECT clip_id FROM segment LIMIT 1")[0]["clip_id"]
    run("transcribe", env, clip_id)  # destructive: r1 IDs can no longer resolve
    r = run("validate", env, "--cut", write_cut(env, seg_ids), expect_ok=False)
    report = json.loads(r.stdout)
    assert r.returncode == 1 and set(report["missing"]) == set(seg_ids)
