# 02 — Data Model

Four object types. The atoms live in SQLite; the organizational objects live in
the vault as markdown that references atoms by ID. Nothing here is final — it's
the starting schema, deliberately minimal, with room noted where v2/v3 grow.

## Objects

### Clip (fact) — a physical media file
The unit of media on disk. Identified by content hash, not path (paths change;
hashes don't).

### Segment (fact) — a contiguous spoken chunk within a clip
Produced by transcription at **sentence/utterance granularity** — the grain that
is both real contiguous audio (so it can round-trip to a timeline) and
editorially meaningful (so selection/reordering is the narrative work). Word-
level timings are stored underneath so trimming is possible later without
re-transcribing.

### Project / Category (judgment) — an organizational unit
An evolving, multi-label tag, **not** a folder. A clip can carry many. The
taxonomy itself is expected to change; treat it as data, not code. Lives as one
markdown file per project in `vault/projects/`.

### Narrative (judgment) — a named, ordered, evolving thread
The most valuable object. A curated, ordered collection of segment/clip
references plus editorial prose, independent of both project (org unit) and
video (rendered output). It is the thing that "updates over time." Lives as one
markdown file per narrative in `vault/narratives/`, referencing IDs.

Relationships are **many-to-many** throughout: one narrative → many videos over
time; one video → many narratives; one clip → many projects and narratives.

## SQLite schema (v1 starting point)

IDs are stable, human-legible strings (e.g. `clip_a1b2c3`, `seg_a1b2c3_r1_0042`)
so they read cleanly inside markdown and cut files.

```sql
CREATE TABLE clip (
    id            TEXT PRIMARY KEY,   -- clip_<hash-prefix>  — IDENTITY, hash-based, immutable
    display_name  TEXT,               -- e.g. projector-build_a1b2c3 — name + hash tail, LABEL not identity
    source_name   TEXT,               -- original filename at intake; PROVENANCE, never identity.
                                      -- Kept because the archive move discards the name, and
                                      -- cross-run take-group pairing needs the _A/_B stem.
    path          TEXT NOT NULL,      -- current known location (may change)
    content_hash  TEXT NOT NULL UNIQUE, -- dedup + integrity + relocation-tolerance
    duration_s    REAL,
    fps           REAL,               -- needed for timecode math on export
    start_tc      TEXT,               -- embedded source timecode if present
    capture_date  TEXT,               -- ISO8601; from metadata, NOT file mtime — the ONE owner of the date
    capture_date_source TEXT,         -- 'embedded' | 'inferred' | 'manual' | 'mtime-fallback'
    codec         TEXT,
    width         INTEGER,
    height        INTEGER,
    clip_summary  TEXT,               -- LLM-derived gist; DERIVED FACT, lives here not in vault
    clip_summary_input_hash TEXT,     -- transcript hash the summary was built from (staleness)
    visual_summary TEXT,              -- LLM gist of keyframe captions; derived fact
    visual_summary_input_hash TEXT,   -- hash of ordered keyframe captions (staleness)
    take_group    TEXT,              -- groups simultaneous angles of ONE take (see below)
    is_canonical_audio INTEGER NOT NULL DEFAULT 1, -- transcribe only the canonical angle
    ingested_at   TEXT NOT NULL,
    transcribed_at TEXT,
    transcribe_gen INTEGER NOT NULL DEFAULT 0  -- bumped on every (re-)transcription
);
-- take_group: the real footage includes Filmic DoubleTake A/B pairs — front +
-- back camera recorded SIMULTANEOUSLY (same timestamp stem, e.g.
-- 08172025_130435_A/_B). These are two angles of one take, not two takes and
-- not dupes. Ingest groups them by filename stem + matching duration; one
-- angle (default _A) is canonical for AUDIO — transcribing both would store
-- the same words twice under different segment IDs. Keyframe captions run on
-- BOTH angles (the visuals genuinely differ). The dup heuristic must skip
-- same-take_group pairs — same duration is expected there, not suspicious.
-- display_name = <topic-hint-if-known>_<hash-prefix>. NO date in the string:
-- the date already lives in `capture_date` (its single owner). Baking it into
-- the name would duplicate data that then drifts when a date is later
-- corrected. Chronological legibility comes from sorting/displaying by
-- `capture_date`, not from the name. The trailing hash prefix guarantees
-- uniqueness, so there is NO error-on-collision path at the clip layer.
-- Identity is always `id` (the hash); the name is legibility only.

CREATE TABLE segment (
    id            TEXT PRIMARY KEY,   -- seg_<clip>_r<gen>_<nnnn>
    clip_id       TEXT NOT NULL REFERENCES clip(id),
    gen           INTEGER NOT NULL,   -- transcription generation this row belongs to
    idx           INTEGER NOT NULL,   -- order within clip
    t_in          REAL NOT NULL,      -- seconds from clip start
    t_out         REAL NOT NULL,
    text          TEXT NOT NULL,      -- verbatim transcript, the authority
    words_json    TEXT,               -- word-level timings, for later trimming
    UNIQUE(clip_id, gen, idx)
);
-- Re-transcription is DESTRUCTIVE by design: bump clip.transcribe_gen, delete
-- the old generation's rows, insert the new. The generation token in the ID is
-- what makes this safe — a stale reference in a narrative or cut can never
-- resolve against the new generation, so `validate` fails LOUDLY instead of
-- silently pointing at different words. Repair is a skill operation (see
-- 06-skill): fuzzy-match the human-readable echo beside each dangling ID
-- against the new segments and propose replacements. No tombstones, no
-- superseded state — the ID format carries the whole guarantee.

CREATE TABLE keyframe (
    id            TEXT PRIMARY KEY,   -- kf_<clip>_<nnnn>
    clip_id       TEXT NOT NULL REFERENCES clip(id),
    t             REAL NOT NULL,      -- seconds from clip start
    caption       TEXT NOT NULL,      -- local VLM caption; derived fact
    model         TEXT NOT NULL,      -- which VLM, so re-captions are tracked
    UNIQUE(clip_id, t)
);
-- Keyframes come from ffmpeg scene detection (fixed-interval fallback for
-- static talking-head shots). Captions are embedded (ref_type 'keyframe') so
-- search covers what's ON SCREEN, not just what was said. Fine-grained B-roll
-- shot tagging stays v3; this table is the seam it grows into.

CREATE TABLE embedding (
    ref_type      TEXT NOT NULL,      -- 'segment' | 'summary' | 'keyframe'
    ref_id        TEXT NOT NULL,
    model         TEXT NOT NULL,      -- which embedder, so re-embeds are tracked
    vec           BLOB NOT NULL,      -- sqlite-vec
    PRIMARY KEY (ref_type, ref_id, model)
);

-- Project membership is a JUDGMENT; this table is a PURE projection of vault
-- truth, kept only for query speed, and holds CONFIRMED memberships only.
-- Classifier proposals live in the review note (vault/review/) until a human
-- confirms them — they never touch this table, which is therefore always
-- rebuildable from the vault by `sync` with zero loss.
CREATE TABLE clip_project (
    clip_id       TEXT NOT NULL REFERENCES clip(id),
    project       TEXT NOT NULL,      -- matches a vault/projects/<slug>.md
    PRIMARY KEY (clip_id, project)
);

-- Near-duplicate clustering (re-exports, trims, proxies): DESCOPED to v2+.
-- Exact dupes are already caught by the UNIQUE content_hash constraint. v1
-- ships a cheap heuristic instead — same duration ±0.5s, OR same capture
-- timestamp where present (re-exports/trims usually carry the original
-- recording date; take_group siblings excluded — they share both by design)
-- → flagged "possible dupe" in the review note for a human call. A
-- dup_cluster table is the seam this grows into if perceptual/audio
-- fingerprinting ever earns its keep.
```

Note the deliberate choice: `clip_project` is a **projection** of vault truth
for fast querying, rebuildable at any time. The vault markdown is authoritative
for judgments; the DB caches them for joins. If they ever disagree, the vault
wins and the table is regenerated — safe precisely because unconfirmed
proposals never live in the DB.

## Vault conventions

### `vault/projects/<slug>.md`
```markdown
---
type: project
slug: studio/projector-build
parent: studio
aliases: ["projector build"]
---
# Projector Build
Prose describing scope, intent, status. Clip membership is queried from the DB
projection, but notable clips can be linked by ID: [[clips/clip_a1b2c3]].
```

### `vault/narratives/<slug>.md`
```markdown
---
type: narrative
slug: learning-to-let-go
status: active           # active | dormant | rendered
spans: [2019, 2026]
projects: [personal/musings]
---
# Learning to Let Go
Editorial prose describing the arc. The ordered thread is a list of segment
references — pointers, not transcript:

## thread
1. seg_a1b2c3_r1_0007   <!-- verbatim echo for humans, not authority -->
2. seg_f4e5d6_r1_0031
3. seg_a1b2c3_r1_0042

## renders
- 2026-07 first cut → [[projects/personal/musings]]
```

### `vault/summaries/…`
Derived, staleness-tracked. Structure and input-hash tracking in
`specs/04-summaries.md`.

### `vault/review/<date>.md` (ephemeral, machine-parsed)
The batch-confirm surface. Each `sync` run writes one checklist: proposed
project memberships (grouped by project, with clip summaries), undated clips,
possible dupes. You tick/untick boxes; `apply-review` parses the note, writes
confirmed memberships to the vault + projection, and archives the note.
Checkbox lines follow a strict format (`- [ ] clip_<id> → <slug> — <echo>`)
because they are parsed, not read.

## Resolved identity & naming decisions

**Two different naming regimes, split by who creates the name and at what volume:**

- **Clips & segments — opaque, hash-based identity; name-only display label.**
  Ingested by the thousand, so identity cannot depend on a human resolving a
  collision. `id = clip_<hash>` / `seg_<clip>_r<gen>_<nnnn>` is immutable and
  machine-only; the `r<gen>` token ties a segment ID to one transcription
  generation, so destructive re-transcription can never silently re-bind an
  old reference to new words. A separate `display_name` (`<topic>_<hashprefix>`) gives
  legibility in Obsidian and cut files; the trailing hash prefix makes it
  collision-proof, so no error path is needed. **No date in the name** — the
  date lives once in `capture_date`; chronology comes from sorting by that
  field, not from a duplicated string that would drift on correction.

- **Projects & narratives — human-readable slugs, unique-on-create.** Authored
  one at a time by you, so a collision is something a human can resolve on the
  spot. **Enforce slug uniqueness and error out on conflict** — that single
  constraint is the whole rename-safety story. `aliases` frontmatter preserves
  old names; don't reuse a retired slug. Obsidian auto-updates `[[links]]` on
  rename within the vault, so in-vault renames propagate for free.

**Opaque IDs for projects/narratives — considered and rejected, deliberately.**
Opaque IDs (`nar_7f3a` + slug as display field) pay off in a DB-backed system
with a UI that renders display names. They *fight* a filename-is-identity tool
like Obsidian: filename = opaque → unreadable `[[nar_7f3a]]` graph (kills the
one reason to use Obsidian); filename = slug → back to rename-fragility and the
opaque ID bought nothing. Since Obsidian-as-graph-UI is a chosen constraint,
slugs+aliases+unique-on-create is the *correct fit*, not a compromise. (This
does not touch clip/segment IDs, which stay opaque — different substrate: DB
atoms, never filenames.)

## Where derived summaries live (resolved)

Clip summaries are **derived facts** (LLM gist of a transcript, regenerable,
staleness-tracked) → they live in SQLite (`clip.clip_summary` +
`clip_summary_input_hash`), **not** in the vault. Narratives *reference* a
clip's summary; they never contain it, so regenerating a summary never edits a
curated file. `vault/clips/` is reserved for optional **human** notes on a clip,
not machine gists. Full staleness mechanics: `specs/04-summaries.md`.

## Flat taxonomy + grouping hints (resolved)

The project taxonomy is **flat** — music, poetry, personal/musings, etc. are
sibling tags, even though some are kept logically separate in the author's head.
To keep the classifier from scattering closely-related clips, projects may
declare informal neighbors:

```markdown
---
type: project
slug: music
related: [poetry, personal/musings]   # classifier hint only, not hierarchy
---
```

`related` is a **hint for classification proposals**, not a parent/child edge.
Storage stays flat; the skill uses `related` to bias membership suggestions
toward the author's informal groupings. Detail in `specs/06-skill.md`.

## Still open (decide before v2)

- Narrative order: markdown thread (chosen) vs. DB projection if a query ever
  needs ordered traversal. Default markdown; project into DB only on demand.
