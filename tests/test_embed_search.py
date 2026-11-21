"""Tests for scripts/embed + scripts/search.

Hermetic: the sentence_transformers stub embeds text as normalized counts of a
tiny vocabulary, so nearest neighbors are constructible by hand. Stub whisper
segments contain "second"; stub captions contain "caption"/"frame"; stub
visual summaries contain "summary".

Run:  uv run --python 3.14 --with pytest pytest tests/
"""

import json
import sqlite3

from conftest import ingest_pair, rows
from conftest import run_script as run


def pipeline(e):
    ingest_pair(e)
    run("transcribe", e)
    run("caption", e)
    return run("embed", e)


def test_embeds_all_three_ref_types(env):
    report = pipeline(env)
    e = report["embedded"]
    # 2 segments on the canonical angle; 1 keyframe + 1 visual summary per angle
    assert e == {"segment": 2, "keyframe": 2, "visual_summary": 2}
    stored = rows(env, "SELECT ref_type, count(*) n FROM embedding GROUP BY ref_type")
    assert {r["ref_type"]: r["n"] for r in stored} == e


def test_incremental_rerun_embeds_nothing(env):
    pipeline(env)
    again = run("embed", env)
    assert sum(again["embedded"].values()) == 0


def test_explicit_clip_reembeds_without_duplicates(env):
    pipeline(env)
    clip_id = rows(env, "SELECT id FROM clip WHERE is_canonical_audio = 1")[0]["id"]
    report = run("embed", env, clip_id)
    assert report["embedded"]["segment"] == 2  # re-done for this clip only
    counts = rows(env, "SELECT ref_id, count(*) n FROM embedding "
                       "GROUP BY ref_type, ref_id, model HAVING n > 1")
    assert counts == []  # delete-then-insert, never accumulate


def test_search_returns_ids_ranked_by_relevance(env):
    pipeline(env)
    r = run("search", env, "second")
    assert r["level"] == "segment" and r["candidates"] == 2
    top = r["results"][0]
    assert top["id"].startswith("seg_") and "_r1_0001" in top["id"]
    assert top["echo"] == "Second sentence here."
    assert {"clip_id", "t_in", "t_out", "score"} <= set(top)
    assert top["score"] > r["results"][1]["score"]


def test_search_keyframe_level(env):
    pipeline(env)
    r = run("search", env, "caption frame", "--level", "keyframe")
    assert r["results"][0]["id"].startswith("kf_")
    assert "t" in r["results"][0]


def test_search_filters_before_ranking(env):
    pipeline(env)
    canonical = rows(env, "SELECT id FROM clip WHERE is_canonical_audio = 1")[0]["id"]
    other = rows(env, "SELECT id FROM clip WHERE is_canonical_audio = 0")[0]["id"]

    scoped = run("search", env, "caption frame", "--level", "keyframe",
                 "--clip", other)
    assert scoped["candidates"] == 1
    assert all(res["clip_id"] == other for res in scoped["results"])

    dated = run("search", env, "second", "--after", "2027-01-01")
    assert dated["candidates"] == 0 and dated["results"] == []

    project = run("search", env, "second", "--project", "music")
    assert project["candidates"] == 0  # no confirmed memberships exist yet

    conn = sqlite3.connect(env.db)
    conn.execute("INSERT INTO clip_project VALUES (?, 'music')", (canonical,))
    conn.commit()
    project = run("search", env, "second", "--project", "music")
    assert project["candidates"] == 2  # both segments live on the tagged clip


def test_search_unset_model_dies(env):
    pipeline(env)
    env.cfg.write_text(env.cfg.read_text().replace(
        'embedder = "stub-org/stub-embedder"', 'embedder = "TBD"'))
    r = run("search", env, "anything", expect_ok=False)
    assert r.returncode == 1 and "bake-off" in r.stderr
