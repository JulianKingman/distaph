# 03 — Roadmap

Three phases. Each is independently useful, and each proves the ground before
the next pours weight on it. Don't build the ambitious top before the base earns
it.

## v1 — Catalog + retrieve

**Goal:** you can *find* anything in the trough.

Scope:
- **Bulk ingest** a directory of clips (old + new). For each: ffprobe metadata,
  content hash, capture-date extraction.
- **Dedup**: content-hash exact dupes. Near-dup clustering is descoped to v2+;
  v1 flags "possible dupes" (duration ±0.5s, or matching capture timestamp
  where present — re-exports/trims usually preserve it; take_group siblings
  excluded) in the review note for a human call.
- **Capture dating**: read embedded/container metadata, NOT file mtime (copies
  carry copy-date). Record the source of the date. Where missing, flag for
  later inference — don't silently fall back to mtime.
- **Transcribe** (local Whisper, off-hours batch). Sentence-grain segments;
  store word-level timings underneath.
- **Classify** into the project taxonomy: LLM proposes memberships into a
  review note; you batch-confirm with checkboxes in Obsidian; nothing is
  applied unconfirmed. Classification is *against your existing taxonomy*, not
  unsupervised discovery (you already have the mental taxonomy).
- **Caption**: keyframes per clip (scene detect) described by a local VLM
  (Qwen2.5-VL via MLX) + a clip-level visual summary, so search covers what's
  on screen, not just what was said. Runs after transcription; nothing blocks
  on it.
- **Embed** segments, summaries & keyframe captions; wire semantic search with
  *filter-before-rank* scoping.
- **`sync`**: the whole pipeline as one chat-triggerable command over the
  external archive drive (intake → content-addressed archive; fails loudly if
  unmounted). See `specs/07-operations.md`.

Exit criteria: drop a folder in, get a searchable catalog out, and "find clips
about X in project Y between 2019–2021" works.

## v2 — Narratives + summaries

**Goal:** you can *assemble* across time.

Scope:
- **Narrative threads** as markdown in `vault/narratives/`, referencing segment
  IDs. Create, extend, re-order — by hand or LLM-proposed.
- **Multi-level summaries** (segment → clip → narrative → corpus) with
  **staleness triggers** (input-hash tracking; regenerate on drift).
- **`cut` upgraded** to pull from the whole archive, not one shoot: the
  segment-selection tool from the original design now queries across projects
  and narratives. Same ID-only contract, same validator, same FCPXML/`.txt`
  outputs into Resolve.

Exit criteria: "make a cut of the 'learning to let go' narrative, chronological
within theme" produces a valid ID list → timeline in Resolve.

## v3 — Suggest + visual + social

**Goal:** the system *proposes*.

Scope:
- **Suggestion**: LLM traverses the summary layer to propose new videos —
  outlines, at most scripts — synthesizing what's been done and what's missing.
- **Fine-grained visual tagging** (the known rabbit hole): basic keyframe
  captions ship in v1; v3 enriches them — shot types, entities, per-segment
  visual tags — growing out of the existing `keyframe` table. Additive; never
  blocked v1/v2.
- **Social signals**: fold in "what resonated" data from platforms as an input
  to suggestion (which past themes to revisit/expand).

Exit criteria: "what should I make next?" returns grounded, archive-aware
proposals with references to real footage.

## Cross-cutting: this is a skill, not an app

The deliverable is `skill/SKILL.md` + `scripts/` + the substrate. The skill does
judgment (classify, propose, select, draft); the scripts do plumbing
(transcribe, probe, hash, embed, emit). Build the scripts as standalone,
testable commands first; the skill orchestrates them. See `specs/06-skill.md`.

## Explicitly deferred (so they don't creep into v1)

- Fine-grained visual/B-roll tagging → v3 (basic keyframe captions are v1).
- Near-dup clustering (perceptual/audio fingerprints) → v2+ if the
  duration/capture-time heuristic proves insufficient.
- Social integration → v3.
- Auto-push into Resolve via scripting API → after manual FCPXML import is
  proven (a stray file on disk is easier to debug than a half-worked API call).
- Any GUI. Obsidian is the graph UI. A thin web view over SQLite is a v2+
  convenience for segment triage at scale, not core.
