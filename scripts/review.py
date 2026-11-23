"""The review note as a list of decisions — the logic behind any review screen.

A review note (vault/review/*.md, written by `sync`) holds checkbox lines in
the grammar `apply-review` understands:

    - [ ] clip_xxx → project/slug — echo        tag a clip with a project
    - [ ] date clip_xxx = YYYY-MM-DD — echo      give a clip its capture date
    - [ ] dupe clip_a ~ clip_b — note            "these are not duplicates"

This module turns those lines into items carrying everything a person needs
to decide — the clip's file, length, date, transcript and keyframe captions —
and writes decisions back into the note as ticked, edited or removed lines.
The note stays the record: `apply-review` is still the only thing that
changes the vault and the database.

It knows nothing about how items are shown, so the launcher's review screen
and any future app share it. `distaph review --json` prints the items.
"""

from __future__ import annotations

import re
import sqlite3
import subprocess
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path

TAG_RE = re.compile(r"^- \[( |x|X)\] (clip_\w+)\s*(?:→|->)\s*([\w./-]+?)(\s+—.*)?$")
DATE_RE = re.compile(r"^- \[( |x|X)\] date (clip_\w+)\s*=\s*(\S+?)(\s+—.*)?$")
DUPE_RE = re.compile(r"^- \[( |x|X)\] dupe (clip_\w+)\s*~\s*(clip_\w+)(.*)$")


@dataclass
class Clip:
    id: str
    name: str = ""
    path: str = ""
    duration_s: float | None = None
    capture_date: str | None = None
    date_source: str | None = None
    projects: list[str] = field(default_factory=list)
    transcript: str = ""
    captions: list[tuple[float, str]] = field(default_factory=list)
    visual_summary: str = ""

    @property
    def exists(self) -> bool:
        return bool(self.path) and Path(self.path).exists()


@dataclass
class Item:
    kind: str            # "tag" | "date" | "dupe"
    line: str            # the line as it is in the note now
    ticked: bool
    clips: list[Clip]
    project: str = ""    # tag: proposed project
    date: str = ""       # date: the date on the line ("YYYY-MM-DD" until filled in)
    note: str = ""       # the line's trailing "— …" text

    @property
    def date_filled(self) -> bool:
        return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}(T[\d:]+)?", self.date))


# ------------------------------------------------------------------ reading

def open_notes(vault: Path) -> list[Path]:
    review = vault / "review"
    if not review.is_dir():
        return []
    return sorted((p for p in review.glob("*.md")
                   if p.name != "resolved-dupes.md" and "status: open" in p.read_text()),
                  reverse=True)


def clip_info(conn: sqlite3.Connection, clip_id: str, lines: int = 8,
              captions: int = 4) -> Clip:
    r = conn.execute("SELECT * FROM clip WHERE id = ?", (clip_id,)).fetchone()
    if r is None:
        return Clip(id=clip_id, name="(not in the database)")
    keys = r.keys()
    c = Clip(id=clip_id, name=r["source_name"] or r["display_name"] or clip_id,
             path=r["path"], duration_s=r["duration_s"], capture_date=r["capture_date"],
             date_source=r["capture_date_source"],
             visual_summary=(r["visual_summary"] or "") if "visual_summary" in keys else "")
    c.projects = [p for (p,) in conn.execute(
        "SELECT project FROM clip_project WHERE clip_id = ? ORDER BY project", (clip_id,))]
    gen = r["transcribe_gen"] if "transcribe_gen" in keys else None
    segs = conn.execute(
        "SELECT text FROM segment WHERE clip_id = ? "
        + ("AND gen = ? " if gen is not None else "") + "ORDER BY idx LIMIT ?",
        (clip_id, gen, lines) if gen is not None else (clip_id, lines)).fetchall()
    c.transcript = " ".join(s["text"].strip() for s in segs)
    c.captions = [(k["t"], k["caption"]) for k in conn.execute(
        "SELECT t, caption FROM keyframe WHERE clip_id = ? ORDER BY t LIMIT ?",
        (clip_id, captions))]
    return c


def load_items(note: Path, conn: sqlite3.Connection) -> list[Item]:
    conn.row_factory = sqlite3.Row
    items = []
    for line in note.read_text().splitlines():
        if m := TAG_RE.match(line):
            tick, cid, slug, echo = m.groups()
            items.append(Item("tag", line, tick != " ", [clip_info(conn, cid)],
                              project=slug, note=(echo or "").lstrip(" —")))
        elif m := DATE_RE.match(line):
            tick, cid, d, echo = m.groups()
            items.append(Item("date", line, tick != " ", [clip_info(conn, cid)],
                              date=d, note=(echo or "").lstrip(" —")))
        elif m := DUPE_RE.match(line):
            tick, a, b, rest = m.groups()
            items.append(Item("dupe", line, tick != " ",
                              [clip_info(conn, a), clip_info(conn, b)],
                              note=rest.strip().lstrip("— ").strip()))
    return items


def untagged_clips(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT count(*) FROM clip WHERE id NOT IN "
                        "(SELECT clip_id FROM clip_project)").fetchone()[0]


# ------------------------------------------------------------------ writing

def _replace_line(note: Path, old: str, new: str | None) -> None:
    lines = note.read_text().split("\n")
    try:
        i = lines.index(old)
    except ValueError:
        raise ValueError("that line changed in the note since it was loaded — reopen review")
    if new is None:
        del lines[i]
    else:
        lines[i] = new
    note.write_text("\n".join(lines))


def _set_tick(line: str, ticked: bool) -> str:
    return re.sub(r"^- \[( |x|X)\]", "- [x]" if ticked else "- [ ]", line, count=1)


def accept(note: Path, item: Item) -> None:
    """Tag: yes. Dupe: not a duplicate. Date: needs a filled-in date first."""
    if item.kind == "date" and not item.date_filled:
        raise ValueError("enter the date first")
    _replace_line(note, item.line, _set_tick(item.line, True))


def undo(note: Path, item: Item) -> None:
    _replace_line(note, item.line, _set_tick(item.line, False))


def reject(note: Path, item: Item) -> None:
    """Tag: no — the proposal is removed from the note."""
    _replace_line(note, item.line, None)


def retag(note: Path, item: Item, slug: str) -> None:
    m = TAG_RE.match(item.line)
    _replace_line(note, item.line, f"- [x] {m.group(2)} → {slug}{m.group(4) or ''}")


def set_date(note: Path, item: Item, value: str) -> None:
    _date.fromisoformat(value[:10])  # raises ValueError on a bad date
    m = DATE_RE.match(item.line)
    _replace_line(note, item.line, f"- [x] date {m.group(2)} = {value}{m.group(4) or ''}")


# ------------------------------------------------------------- previewing

def thumbnail(cache: Path, clip: Clip) -> Path | None:
    """A frame from the clip, cached. Uses the first captioned keyframe (known
    to be a good frame), else a third of the way in."""
    if not clip.exists:
        return None
    out = cache / f"{clip.id}.jpg"
    if out.exists():
        return out
    cache.mkdir(parents=True, exist_ok=True)
    t = clip.captions[0][0] if clip.captions else (clip.duration_s or 3) / 3
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", clip.path,
                        "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "4", str(out)],
                       capture_output=True, timeout=60)
    return out if r.returncode == 0 and out.exists() else None


def play(clips: list[Clip]) -> bool:
    """Open clips in QuickTime Player, one window each, so a possible
    duplicate pair can be watched side by side.

    Not `qlmanage -p`: on macOS 26 its video previewer crashes on every clip
    ("Setting highlightedTimeRanges is not supported in your app")."""
    paths = [c.path for c in clips if c.exists]
    if not paths:
        return False
    r = subprocess.run(["open", "-a", "QuickTime Player", *paths],
                       capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        raise RuntimeError(f"QuickTime Player didn't open: {r.stderr.strip()}")
    return True
