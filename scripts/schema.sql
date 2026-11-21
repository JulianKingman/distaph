-- v1 schema — authoritative definition in specs/02-data-model.md.
-- Applied idempotently by scripts/common.py on every DB open.

CREATE TABLE IF NOT EXISTS clip (
    id            TEXT PRIMARY KEY,   -- clip_<hash-prefix>
    display_name  TEXT,               -- <topic>_<hash-prefix>; label, not identity
    source_name   TEXT,               -- original filename at intake (provenance; take-group pairing)
    path          TEXT NOT NULL,      -- current known location
    content_hash  TEXT NOT NULL UNIQUE,
    duration_s    REAL,
    fps           REAL,
    start_tc      TEXT,               -- embedded source timecode if present
    capture_date  TEXT,               -- ISO8601; from metadata, NOT file mtime
    capture_date_source TEXT,         -- 'embedded' | 'inferred' | 'manual' | 'mtime-fallback'
    codec         TEXT,
    width         INTEGER,
    height        INTEGER,
    clip_summary  TEXT,
    clip_summary_input_hash TEXT,
    visual_summary TEXT,
    visual_summary_input_hash TEXT,
    take_group    TEXT,               -- groups simultaneous angles of ONE take
    is_canonical_audio INTEGER NOT NULL DEFAULT 1,
    ingested_at   TEXT NOT NULL,
    transcribed_at TEXT,
    transcribe_gen INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS segment (
    id            TEXT PRIMARY KEY,   -- seg_<clip>_r<gen>_<nnnn>
    clip_id       TEXT NOT NULL REFERENCES clip(id),
    gen           INTEGER NOT NULL,
    idx           INTEGER NOT NULL,
    t_in          REAL NOT NULL,
    t_out         REAL NOT NULL,
    text          TEXT NOT NULL,
    words_json    TEXT,
    UNIQUE(clip_id, gen, idx)
);

CREATE TABLE IF NOT EXISTS keyframe (
    id            TEXT PRIMARY KEY,   -- kf_<clip>_<nnnn>
    clip_id       TEXT NOT NULL REFERENCES clip(id),
    t             REAL NOT NULL,
    caption       TEXT NOT NULL,
    model         TEXT NOT NULL,
    UNIQUE(clip_id, t)
);

CREATE TABLE IF NOT EXISTS embedding (
    ref_type      TEXT NOT NULL,      -- 'segment' | 'summary' | 'keyframe'
    ref_id        TEXT NOT NULL,
    model         TEXT NOT NULL,
    vec           BLOB NOT NULL,
    PRIMARY KEY (ref_type, ref_id, model)
);

CREATE TABLE IF NOT EXISTS clip_project (
    clip_id       TEXT NOT NULL REFERENCES clip(id),
    project       TEXT NOT NULL,
    PRIMARY KEY (clip_id, project)
);
