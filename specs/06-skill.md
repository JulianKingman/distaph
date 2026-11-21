# 06 — The Skill

This is the deliverable. Not an app — a **skill** (`skill/SKILL.md`) that does
the *judgment* work by orchestrating deterministic *plumbing* scripts over the
fact/judgment substrate. This spec defines what the skill is allowed to do, what
it must never do, and the contracts at each boundary.

## The division of labor

- **Plumbing (`scripts/`)** — deterministic, testable, no judgment. The skill
  *invokes* these; it never reimplements them in-context.
    - `ingest` — probe (ffprobe), hash, capture-date extract, move intake →
      content-addressed archive (the one sanctioned move — nothing references
      the file yet), write clip rows, flag possible dupes (duration ±0.5s or
      matching capture timestamp; take_group siblings excluded).
    - `transcribe` — local Whisper batch → sentence-grain segments + word
      timings. Re-runs bump `transcribe_gen` and destructively replace the old
      generation's rows (see `02-data-model`).
    - `caption` — keyframe extraction (scene detect) + local VLM captions +
      clip-level visual summary.
    - `embed` — segment, summary & keyframe embeddings → sqlite-vec.
    - `search` — filter-before-rank retrieval; returns IDs (see `05-retrieval`).
    - `summarize` — (re)generate stale summaries walking the DAG (see `04`).
    - `build` — resolve an ID list → FCPXML/OTIO (or IntelliScript `.txt`).
    - `validate` — every ID in a cut/narrative resolves in the DB, `t_in`/`t_out`
      fall inside the clip's duration, and the human-readable echo beside each
      ID still matches the transcript (warn on drift).
    - `sync` — the whole fact pipeline in one command (ingest → transcribe →
      caption → embed → propose classifications → write review note →
      auto-commit the vault). Chat-triggered or run by hand; fails loudly if
      the archive drive is unmounted. This is the only entry point you use
      day-to-day; the scripts above are its internals.
- **Skill (judgment)** — classify clips, propose/maintain narratives, draft
  outlines & scripts, select segments for a cut. Probabilistic, and therefore
  *fenced by the ID contract below*.

The skill's job is to decide *which* IDs; the plumbing's job is to turn IDs into
files and files into IDs. Neither crosses into the other.

## The non-negotiable contract: the skill emits IDs, never content-as-data

Everywhere the skill's output will touch real footage — a cut, a narrative
thread, a summary citation — it emits **segment/clip IDs**, and `validate`
confirms each one exists before the output is trusted. The skill may write prose
freely (outlines, summaries, editorial notes), but any claim that *specific
words were spoken* or that *a line belongs in a cut* is an ID, checked.

**Concretely, for a cut:** the skill returns an ordered JSON array of segment
IDs. It does not return transcript text as authority; the `.txt`/FCPXML is
*reconstructed by plumbing* from the DB by resolving those IDs. Rewording is
structurally impossible because the skill has no channel to emit script text —
only references. A hallucinated ID fails `validate` and is rejected, never
reaching a timeline. This is the same property from the very first cut-tool
design, now the law of the whole system.

### Why this survives hand-editing
Because a human editing the cut file / narrative thread is *also* constrained to
IDs, delete-and-reorder is safe by construction. You cannot type a sentence that
was never spoken, because you are not typing sentences — you are ordering
pointers.

## Skill operations (v1→v3)

### classify (v1)
Input: a clip's transcript (+ its clip summary once available). Output: proposed
project membership(s) with a confidence each.
- Classification is **against the existing flat taxonomy**, not unsupervised
  discovery — the taxonomy already reflects the author's mental model.
- Use each project's `related:` frontmatter as a **hint**: bias toward
  co-assigning near-neighbor tags (music ↔ poetry ↔ personal/musings) rather
  than scattering related clips. `related` is a hint, not a hierarchy — it never
  forces membership, only nudges proposals.
- **Propose, then batch-confirm — never auto-file.** Proposals are written to
  the review note (`vault/review/`), grouped by project with clip summaries, as
  strict checkbox lines. Nothing touches the vault or the `clip_project`
  projection until the human ticks the box and `apply-review` runs. One
  skim-and-confirm pass in Obsidian replaces confidence thresholds and
  quarantine states entirely — reviewing 50 proposals takes minutes; the DB
  stays a pure projection of confirmed vault truth.

### repair (v1)
After a destructive re-transcription, references to the old generation's
segment IDs in narratives and cuts fail `validate` (the `r<gen>` token
guarantees they cannot resolve). `repair` fuzzy-matches each dangling
reference's human-readable echo against the clip's new segments and proposes
replacements — as checkbox lines in the review note, human-confirmed like any
other judgment.

### narrate (v2)
Propose or extend a narrative thread: an ordered list of segment IDs plus arc
prose. Writes the human-owned prose to the narrative markdown and the derived
gist to that file's generator-owned `## auto-summary` block (never clobbering
authored prose — see `04-summaries`). Ordering is a judgment; it lives in the
markdown thread, hand-editable.

### cut (v2)
Given a target (a narrative, a shoot, a theme + scope), retrieve candidate
segments (`search`, filter-before-rank), select and order them, emit the ID
list, `validate`, then `build`. Two build targets from the *same* ID list:
`--fcpxml` (deterministic, we already know every timecode) or `--txt` (hand to
IntelliScript). FCPXML is preferred for disjoint single-instance footage; `.txt`
only if the user wants zero timecode handling. Manual import first; `--push` via
Resolve scripting API only once import is proven.

### suggest (v3)
Traverse the summary layer (corpus → narrative) to propose new videos —
outlines, at most scripts — grounded in real material (every proposal cites
segment/clip IDs). Optionally fold in social "what resonated" signals as a bias
over which themes to revisit.

## What the skill must refuse to do

- Emit transcript text as the authority for a cut (must emit IDs).
- Apply a classification or repair the human hasn't confirmed via the review
  note (propose-then-batch-confirm, always).
- Move or rename media files (reference-never-relocate; `01-architecture`).
- Overwrite authored narrative prose when regenerating a summary (write only to
  the generator-owned block).
- Treat a summary as ground truth (must resolve IDs to transcript for any
  content claim).

## SKILL.md shape (to be written)

The `skill/SKILL.md` will encode: the ID-only contract as the first and loudest
rule; a short description of each operation and which script it calls; the
review-note contract (strict checkbox lines, `apply-review` as the only write
path for judgments); and worked examples of the cut ID-list format
and the validate→build handoff. Keep it declarative and example-driven — the
skill reads it as operating instructions, so the invariants must be stated as
hard rules, not aspirations.

## Build order for the skill

1. Stand up `scripts/` as standalone CLIs (ingest → transcribe → caption →
   embed → search → build → validate → sync), each testable in isolation on
   one real clip.
2. Write `SKILL.md` to orchestrate them for `classify` and `cut` first (the v1/
   early-v2 core).
3. Add `narrate`, `summarize`, `suggest` as the substrate above them fills in.

The scripts are boring and reliable; the skill is thin and fenced. That's the
whole point of "skill, not app": most of the system is deterministic, and the
probabilistic part can only ever emit checkable pointers.
