"""Tests for scripts/sync + scripts/apply-review.

Hermetic: child stages run on this interpreter (SYNC_CHILD_PYTHON) with the
model stubs. The vault is a tmp dir (not a git repo — commits report skipped).

Run:  uv run --python 3.14 --with pytest pytest tests/
"""

import json
import re

from conftest import ingest_pair, make_clip, rows
from conftest import run_script as run


def note_path(report):
    return report["note"]


def test_sync_chains_stages_and_writes_note(env):
    make_clip(env.intake / "01012026_120000_A.mov", duration=3, freq=440,
              creation_time="2026-01-01T12:00:00.000000Z")
    make_clip(env.intake / "01012026_120000_B.mov", duration=3, freq=445,
              creation_time="2026-01-01T12:00:00.000000Z")
    make_clip(env.intake / "undated.mov", duration=6, freq=660)  # no creation_time
    report = run("sync", env)

    assert report["failed_stages"] == []
    assert report["stages"]["ingest"]["ingested"] and \
           report["stages"]["transcribe"]["transcribed"]
    assert rows(env, "SELECT count(*) n FROM embedding")[0]["n"] > 0
    assert "not a git repository" in report["vault_commit"]

    text = open(note_path(report)).read()
    assert "## ingested" in text and "## proposals" in text
    undated_clip = rows(env, "SELECT id FROM clip WHERE capture_date IS NULL")[0]["id"]
    assert f"- [ ] date {undated_clip} = YYYY-MM-DD" in text


def test_sync_skip_and_idempotent_rerun(env):
    ingest_pair(env)
    first = run("sync", env, "--skip", "caption", "--skip", "embed")
    assert first["stages"]["caption"] == {"skipped": True}
    assert rows(env, "SELECT count(*) n FROM keyframe")[0]["n"] == 0

    again = run("sync", env)
    assert again["failed_stages"] == []
    assert again["stages"]["ingest"]["ingested"] == []  # nothing new
    assert again["stages"]["transcribe"]["transcribed"] == []


def test_apply_review_membership_date_and_archive(env):
    ingest_pair(env)
    make_clip(env.intake / "undated.mov", duration=6, freq=660)
    report = run("sync", env)
    (env.vault / "projects" / "music.md").write_text(
        "---\ntype: project\nslug: music\n---\n# Music\nProse.\n")

    clip = rows(env, "SELECT id FROM clip WHERE is_canonical_audio = 1 "
                     "AND capture_date IS NOT NULL")[0]["id"]
    undated = rows(env, "SELECT id FROM clip WHERE capture_date IS NULL")[0]["id"]
    note = note_path(report)
    with open(note, "a") as f:
        f.write(f"\n- [x] {clip} -> music — my note here\n")
    text = open(note).read().replace(
        f"- [ ] date {undated} = YYYY-MM-DD", f"- [x] date {undated} = 2026-02-03")
    open(note, "w").write(text)

    result = run("apply-review", env, note)
    assert result["ok"] and len(result["applied"]) == 2

    assert rows(env, "SELECT * FROM clip_project")[0] == \
        {"clip_id": clip, "project": "music"}
    project_text = (env.vault / "projects" / "music.md").read_text()
    assert "## clips" in project_text and clip in project_text
    dated = rows(env, f"SELECT capture_date, capture_date_source FROM clip "
                      f"WHERE id = '{undated}'")[0]
    assert dated == {"capture_date": "2026-02-03T00:00:00",
                     "capture_date_source": "manual"}
    # clean apply archives the note
    assert not re.search(r"status: open", open(result["archived_to"]).read())
    assert not (env.vault / "review").joinpath(note.split("/")[-1]).exists()


def test_apply_review_partial_failure_keeps_note(env):
    ingest_pair(env)
    report = run("sync", env)
    clip = rows(env, "SELECT id FROM clip LIMIT 1")[0]["id"]
    note = note_path(report)
    with open(note, "a") as f:
        f.write(f"\n- [x] {clip} → nonexistent/project\n"
                f"- [x] dupe clip_aaaa1111 ~ clip_bbbb2222\n")

    r = run("apply-review", env, note, expect_ok=False)
    result = json.loads(r.stdout)
    assert r.returncode == 1 and not result["ok"]
    assert "no project note" in result["failed"][0]["error"]
    assert result["applied"] == [{"dupe_dismissed": "clip_aaaa1111 ~ clip_bbbb2222"}]
    assert (env.vault / "review" / "resolved-dupes.md").exists()
    assert open(note).read()  # note stays in place for a fix + re-run


def test_dismissed_dupes_stay_dismissed_across_syncs(env):
    make_clip(env.intake / "one.mov", duration=4, freq=440,
              creation_time="2026-03-01T10:00:00.000000Z")
    make_clip(env.intake / "two.mov", duration=4, freq=550,
              creation_time="2026-03-02T10:00:00.000000Z")
    first = run("sync", env)
    a, b = [r["id"] for r in rows(env, "SELECT id FROM clip ORDER BY id")]
    text = open(note_path(first)).read()
    pair = re.search(r"- \[ \] dupe (clip_\w+) ~ (clip_\w+)", text)
    assert pair and {pair.group(1), pair.group(2)} == {a, b}

    ticked = text.replace(pair.group(0), pair.group(0).replace("[ ]", "[x]"))
    open(note_path(first), "w").write(ticked)
    run("apply-review", env, note_path(first))

    second = run("sync", env)
    assert "dupe" not in open(note_path(second)).read().split("## proposals")[0]
