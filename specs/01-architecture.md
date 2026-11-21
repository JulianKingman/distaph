# 01 — Architecture

## Purpose of this document

Capture the load-bearing structural decisions and *why* they hold, so that
future changes don't quietly violate them. If you change something here, you're
changing the foundation — do it deliberately.

## Principle 1: Two layers, one seam

The system is two layers that want different substrates:

- **Fact layer** — high-volume, machine-generated, objective, queryable.
  Transcript segments, timecodes, capture dates, codecs, content hashes,
  embeddings. Lives in **SQLite** (+ a vector store).
- **Judgment layer** — lower-volume, human/LLM-curated, subjective, evolving.
  Project membership, narrative order, take quality, multi-level summaries.
  Lives in **markdown-in-git**, surfaced through **Obsidian**.

**The rule:** facts are regenerable and must never be destroyed by curation;
judgments are curated and must never be destroyed by re-cataloging. You can
re-transcribe or re-embed the entire trough without touching a single human
decision, and you can re-tag or re-order narratives without corrupting a single
transcript. The two operations are orthogonal by construction.

### Why not one store?

- *Everything in git*: thousands of Whisper segments as markdown is bloat and
  merge pain, and you get no query surface.
- *Everything in SQLite*: you lose diffable, human-editable, graph-traversable
  prose — the thing Obsidian and LLMs are both good at.

Split by **mutability and consumer**, and the tension dissolves.

## Principle 2: IDs are the only load-bearing link

Across the seam, the connection is always an **ID**, never copied data.

- Markdown (judgment) contains prose + segment/clip IDs. It never contains
  ground-truth transcript text as authority — only as human-readable echo.
- SQLite (fact) is the source of truth for what any ID resolves to.
- The LLM, when producing anything that will touch real footage (a cut, a
  narrative membership, a summary citation), **emits IDs**. A validator
  confirms every ID exists before the output is trusted.

This is the same discipline that makes the cut tool hallucination-safe, scaled
to the whole archive. It is non-negotiable: it's the property that lets an LLM
operate over the corpus without fabricating footage.

## Principle 3: Reference, never relocate

Physical file storage is decoupled from logical organization.

- Clips stay where they are (or in a flat, content-addressed store keyed by
  hash). They are **never moved into project/narrative folders.**
- All organization is references (DB rows, markdown links) pointing at clips
  by path + hash.

### Why

- A single clip can belong to **many** projects and narratives. A folder tree
  can represent only one membership. Multi-membership is the normal case here
  (a music clip that's also a personal vlog musing; a photo-booth event that's
  also B-roll for a studio project).
- Moving files breaks every existing reference and every relink in Resolve.
- Content-addressing (hash) makes dedup, integrity checks, and relocation-
  tolerance free.

## Principle 4: Plumbing vs. skill

Two kinds of work, kept apart:

- **Deterministic plumbing** (`scripts/`) — transcription, ffprobe metadata,
  hashing, dedup clustering, embedding, FCPXML/OTIO emission, DB writes. No
  judgment. Reproducible. An LLM should *call* these, not perform them.
- **Judgment** (`skill/`) — classification, narrative proposal/maintenance,
  outline/script drafting, segment selection for a cut. This is the LLM's job,
  expressed as a skill that orchestrates the plumbing.

This mirrors the fact/judgment seam at the behavioral level: plumbing acts on
facts, the skill produces judgments. It also means most of the system is boring,
testable scripts, and only a thin orchestration layer is probabilistic.

## Principle 5: Derived artifacts must track staleness

Summaries (segment → clip → narrative → corpus) are **derived** from facts +
judgments below them. When an input changes (a clip is re-tagged, a narrative
re-ordered), summaries above it are silently wrong, and an LLM traversing them
reads a stale map.

**Every derived artifact records the hashes of its inputs and is regenerated
when they drift.** Staleness is detected, not hoped away. See
`specs/04-summaries.md`.

## Consequences for retrieval

- Scale is modest (10^4–10^5 segments): exact brute-force vector search is
  fast enough; no ANN index needed. See `specs/05-retrieval.md`.
- The real risks are **semantic clumping** (similar-sounding vlog musings) and
  **granularity** (segment embeddings find lines; summary embeddings find
  themes). Fix by *filtering before ranking* (scope by project/date/narrative,
  then rank) and by embedding the summary layer separately.

## What off-the-shelf tools do and don't cover

- **Editing step** (rough cut from selected lines): Resolve Studio's
  IntelliScript, or Eddie/Gling, remain viable. We reuse, not rebuild, here.
- **Archive/knowledge layer** (this project): nothing off the shelf does
  LLM-native narrative traversal + cross-year assembly. DAMs catalog assets but
  aren't LLM-shaped and don't do narrative or assembly. This is why the custom
  build is justified — but only for this layer, and it still reuses Whisper,
  embeddings, PySceneDetect, and Obsidian-as-graph-UI rather than building those.
