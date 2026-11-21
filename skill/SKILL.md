---
name: distaph
description: >
  Operate the user's Distaph library: sync new footage through the fact pipeline,
  propose project classifications for review, search the corpus, assemble and
  validate cuts, and maintain narratives. Use when the user says "sync",
  "apply review", asks to find/search footage or lines, wants a cut/edit/
  timeline built, or works with clips, segments, narratives, or the vault.
---

# Distaph — operating instructions

You orchestrate deterministic plumbing (the `distaph` commands) over a fact
layer (SQLite: `db/archive.sqlite`) and a judgment layer (the markdown vault,
surfaced in Obsidian). You are working inside the user's **library** folder;
paths below (`vault/`, `cuts/`, `facts/`) are relative to it. The app lives
elsewhere — never edit it from here. Your job is judgment: choosing, ordering, proposing. The
scripts' job is facts: probing, transcribing, resolving IDs into files.
Never do a script's job in-context, and never let judgment bypass the
review flow.

## LAW 1 — The ID-only contract

Anywhere your output will touch real footage — a cut, a narrative thread, a
claim that specific words were spoken — you emit **segment/clip IDs**
(`seg_<clip>_r<gen>_<nnnn>`, `clip_<hash>`) taken verbatim from a script's
output (`search`, SQL over the DB). You never construct an ID, never quote
transcript text as authority, and every ID list passes `distaph validate`
before `distaph build`. A hallucinated ID fails validation and must be
reported, not repaired silently.

You may write prose freely (summaries, outlines, editorial notes, suggested
lines to record) — prose is allowed to propose things that don't exist, IDs
are not.

## LAW 2 — Judgments only land via the review note

Classification proposals, date fixes, dupe dismissals: written as checkbox
lines to the open review note in `vault/review/`, applied only by
`distaph apply-review` after the human ticks them. Never write to
`clip_project`, project notes, or `capture_date` directly.

## LAW 3 — Never move, rename, or modify media

Archive files are content-addressed and referenced everywhere. Denoising,
color, reframing: edit-time operations in Resolve, never on the originals.

## Operations

### sync (the day-to-day entry point)
1. Run `distaph sync` (chains ingest → transcribe → caption → embed; writes
   the review note; exports facts and commits the library). Drive unmounted = it fails loudly —
   report that, don't work around it.
2. Read the note it wrote. For each newly ingested clip, read its transcript
   (`SELECT text FROM segment WHERE clip_id=? ORDER BY idx`) and summaries,
   then classify against the taxonomy: the `vault/projects/**.md` files ARE
   the taxonomy (flat; `related:` frontmatter is a proposal-bias hint, not a
   hierarchy — prefer co-assigning related tags over scattering).
3. Append proposals to the note's `## proposals` section, one strict line
   each, echo included:
   `- [ ] clip_a1b2c3d4e5f6 → music/originals — recording the charango bridge take`
4. Tell the user the note is ready to skim in Obsidian. Do not tick boxes.

### apply review
Run `distaph apply-review <note>` when the user says to. Report what applied,
what failed and why, what carried forward. Unticked = not yet decided — never
nag, never re-propose with different wording to force a decision.

### search
`distaph search "query" [--level segment|keyframe|visual_summary] [--project
slug ...] [--after ISO] [--before ISO] [--clip id ...]`. Filter before rank:
scope by project/date/clips whenever the request implies one. Results are
IDs + echoes; to quote what was actually said, resolve the ID in the DB.

### cut
1. Gather candidates with `search` (segment level; keyframe level for B-roll).
2. Select and order — this is editorial judgment. Consult
   `vault/editorial-notes.md` and honor it. Standing rules: rhythm beats
   completeness; drop asides that break the through-line unless one is the
   closing beat; breathing room is handled by build's default `--pad` (0.25s)
   — don't compensate for it.
3. Write the cut JSON to `cuts/<name>.json` (versioned; it's a judgment): `{"name": "...", "segments": [{"id": "seg_...",
   "pip": true|false}, ...]}` — `pip` overlays the take-group sibling angle.
4. `distaph validate --cut cuts/<name>.json` — must pass before building.
5. `distaph build cuts/<name>.json --fcpxml cuts/<name>.fcpxml` (or `--txt` for
   IntelliScript). Hand the user the file path for manual Resolve import.
6. After the user reviews, disposition every piece of feedback: taste goes in
   `vault/editorial-notes.md`; tooling problems become a drafted GitHub issue
   for the Distaph repo (the user files it). Every time.

### narrate
Propose or extend `vault/narratives/<slug>.md`: ordered ID thread with echo
comments (`1. seg_... <!-- verbatim echo -->`), your arc prose, and explicit
gap entries for missing material:
`- NEEDED: 30s project recap — draft: "Last summer I started
building a projector..."` (suggested B-roll gaps cite real keyframe/clip IDs from
search). Auto-generated gists go only under a `## auto-summary` heading —
never touch the human's prose. Validate the thread after editing:
`distaph validate --narrative <file>`.

### repair
After re-transcription, `validate` reports old-generation IDs as missing —
that is the system working. For each dangling ID, fuzzy-match its echo text
against the clip's current segments (`SELECT id, text FROM segment WHERE
clip_id=?`) and append replacement proposals to the review note:
`- [ ] seg_old_r1_0007 → becomes seg_old_r2_0006 — echo text` — wait for
confirmation like any judgment. (Grammar note: repair lines are proposals for
the human; apply them by editing the narrative only after ticking.)

## Worked example — from ask to timeline

User: "make me a short cut of the projector build, rear cam overlay"

```
distaph search "projector build" --level segment          # + visual_summary pass
# → pick IDs, order them editorially, then:
cat > cuts/projector-build.json <<'EOF'
{"name": "projector-build", "segments": [
  {"id": "seg_fe2298880c97_r1_0000", "pip": true},
  {"id": "seg_18cc16b61141_r1_0019", "pip": true}
]}
EOF
distaph validate --cut cuts/projector-build.json     # ok:true required
distaph build cuts/projector-build.json --fcpxml cuts/projector-build.fcpxml
```

Report: what's in the cut and why, the file path, and what you left out.

## Refuse, always

- Emitting transcript text as authority for a cut (IDs only).
- Applying any judgment the human hasn't ticked (LAW 2).
- Moving/renaming/modifying media (LAW 3).
- Treating a summary as ground truth — resolve IDs down to transcript for
  any content claim.
- Guessing Resolve FCPXML dialect parameters — tune empirically against a
  Resolve-authored export (see PIP_POSITION history in the app's scripts/build).
