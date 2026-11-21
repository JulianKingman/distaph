# 04 — Summaries

Summaries are the map the LLM traverses to find and propose material. They are
**derived artifacts** — never authored, always regenerated — and their single
hard requirement is that a stale summary must be *detectable*, because an LLM
reading a stale map fabricates confidently.

## The levels

```
segment  → (raw transcript, not a summary; the atom)
clip     → gist of one clip's transcript                  [SQLite: clip.clip_summary]
narrative→ gist of a narrative's arc across its segments  [derived from the thread]
corpus   → gist of the whole archive by project/theme     [top-level map]
```

Each level summarizes the level(s) below it. Higher levels are what power
"suggest a new video" (theme-level retrieval); lower levels power "find the
exact line" (segment retrieval).

## Staleness: the core mechanic

**Every summary records the hash(es) of its inputs and is regenerated when they
drift.** Detected, not hoped away.

- **Clip summary** input = the clip's ordered segment text. Store
  `clip_summary_input_hash = hash(concat(segment.text order by idx))`. On any
  re-transcription, the hash changes → summary flagged stale → regenerate.
- **Clip visual summary** input = the clip's ordered keyframe captions; same
  mechanic via `visual_summary_input_hash`. Re-captioning (new VLM) flips it.
- **Narrative summary** input = the ordered thread (list of segment IDs) + the
  clip summaries of the clips it touches + the narrative's own editorial prose.
  Hash all three. Re-ordering the thread, re-tagging a member clip, or editing
  the prose all flip the hash.
- **Corpus summary** input = the set of narrative summaries + project
  membership projection. Changes when narratives change or clips are re-tagged.

The dependency is a DAG: segment → clip → narrative → corpus. A change at any
node marks everything *above* it stale. Regeneration walks up from the change.

## Where each summary lives

| Level | Store | Why |
|---|---|---|
| clip | SQLite `clip.clip_summary` | pure derived fact, queryable, no human edits |
| narrative | markdown body is *curated*; the derived gist is a fenced/frontmatter block or a sibling `summaries/` file | the arc prose is yours; the auto-gist is derived — keep them distinguishable |
| corpus | `vault/summaries/_corpus.md` (derived) | a readable top map for both you and the LLM |

Rule of thumb (from `01-architecture`): **if a human hand-edits it, markdown; if
only a script writes it, SQLite or a clearly-marked derived block.** The narrative
file is the one hybrid — human arc prose + a derived gist — so mark the derived
part explicitly (e.g. under a `## auto-summary` heading the generator owns) so
regeneration never clobbers your writing.

## Regeneration triggers

- After a (re-)transcription batch → recompute affected clip summaries.
- After a classification change (clip re-tagged) → mark affected narrative &
  corpus summaries stale.
- After a narrative thread/prose edit → mark that narrative + corpus stale.
- A `summaries refresh` command walks the DAG and regenerates only stale nodes.

Cheap check: store input hashes; compare on demand; regenerate misses. No need
to watch the filesystem — recompute-on-command is enough at this scale.

## What a summary must and must not contain

- **Must**: prose gist + references (segment/clip IDs) to the material it
  covers, so the LLM can drill from theme → exact line.
- **Must not**: be treated as authority for *what was said*. The transcript is
  authority. A summary is a lossy pointer-rich index, and any claim it makes
  about specific content is verified by following its IDs down to segments.

This preserves the pointer discipline at the summary layer: summaries help the
LLM *navigate*, but the moment it needs ground truth it resolves IDs to
transcript.
