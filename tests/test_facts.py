"""export-facts / import-facts round-trip (specs/08-library-and-launcher.md)."""

import json
import sqlite3

from conftest import make_clip, run_script


def table(db, sql):
    c = sqlite3.connect(db)
    c.row_factory = sqlite3.Row
    return [dict(r) for r in c.execute(sql)]


def test_round_trip_rebuilds_facts_without_embeddings(env, tmp_path):
    make_clip(env.intake / "a.mov", duration=4, freq=440,
              creation_time="2024-05-01T10:00:00Z")
    run_script("sync", env)
    before = {t: table(env.db, f"SELECT * FROM {t} ORDER BY 1")
              for t in ("clip", "segment", "keyframe")}
    assert before["segment"]

    out = tmp_path / "facts"
    rep = run_script("export-facts", env, "--out", str(out))
    assert rep["rows"]["segment"] == len(before["segment"])
    lines = (out / "segment.jsonl").read_text().splitlines()
    assert [json.loads(l)["id"] for l in lines] == sorted(json.loads(l)["id"] for l in lines)

    # export is deterministic: a second run is byte-identical
    first = (out / "clip.jsonl").read_bytes()
    run_script("export-facts", env, "--out", str(out))
    assert (out / "clip.jsonl").read_bytes() == first

    env.db = tmp_path / "rebuilt.sqlite"
    rep = run_script("import-facts", env, "--from", str(out))
    assert rep["rows"]["clip"] == len(before["clip"])
    for t, rows in before.items():
        assert table(env.db, f"SELECT * FROM {t} ORDER BY 1") == rows
    assert table(env.db, "SELECT count(*) n FROM embedding")[0]["n"] == 0


def test_import_refuses_nonempty_db_without_replace(env, tmp_path):
    make_clip(env.intake / "a.mov", duration=3, freq=550)
    run_script("sync", env)
    out = tmp_path / "facts"
    run_script("export-facts", env, "--out", str(out))
    r = run_script("import-facts", env, "--from", str(out), expect_ok=False)
    assert r.returncode == 1 and "--replace" in r.stderr
    rep = run_script("import-facts", env, "--from", str(out), "--replace")
    assert rep["rows"]["clip"] == 1
