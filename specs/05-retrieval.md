# 05 — Retrieval

Retrieval is what makes "include relevant past material" and "suggest across the
archive" actually function. The design is shaped by two facts: the scale is
small, and the content is *self-similar* (a lot of vlog musings that sound alike
in embedding space).

## Scale: no ANN index needed

At sentence grain the whole archive is ~10^4–10^5 segments. Brute-force **exact**
cosine over every candidate vector is milliseconds at that size, and exact beats
approximate (HNSW/IVF) on recall. ANN indexes earn their complexity at tens of
millions of vectors — not here. Use `sqlite-vec` with exact search; revisit only
if the corpus grows orders of magnitude.

## The real risk: semantic clumping

A large trough of thematically-similar personal content embeds into a tight
cluster. Pure top-k cosine then returns "mush" — technically-similar segments
that don't answer the actual need. Two mitigations, used together:

### 1. Filter before rank (the primary lever)

Never rank over the whole corpus when you can scope first. The metadata layer
makes this cheap:

```
candidates = segments
    WHERE project IN (...)        -- scope to relevant projects
      AND capture_date BETWEEN .. -- and/or a time window
      AND clip_id IN (narrative's members)   -- and/or a narrative
then rank candidates by cosine to the query embedding
```

Scoping *before* similarity turns "find the closest of everything" (mush) into
"find the closest of the relevant set" (signal). This is why the metadata /
judgment layer is a retrieval feature, not just organization.

### 2. Three embedding granularities (find lines vs. themes vs. visuals)

- **Segment embeddings** → precise, "find the exact line about X." Good for
  building a cut.
- **Summary embeddings** (clip & narrative level, from `04-summaries`) →
  thematic, "find past *threads* that resonate with this new capture." Good for
  suggestion and for pulling in relevant past material.
- **Keyframe-caption embeddings** → visual, "find the clip where I'm at the
  beach" — works even when the thing was never said aloud. Good for B-roll
  hunting and footage you shot but didn't narrate.

Querying the summary layer sidesteps segment-level clumping because summaries
compress away the surface self-similarity and keep the distinguishing theme.

## Query patterns by use case

| Use case | Scope filter | Embedding level |
|---|---|---|
| Build a cut from a shoot | this shoot's clips (+ optional narrative) | segment |
| Pull relevant past B-roll/lines into a new video | project + date window | segment, then summary to widen |
| "What past narratives relate to this capture?" | none or broad project set | summary (narrative) |
| "What should I make next?" | corpus | summary (corpus → narrative) |
| Find B-roll / "the shot where…" | optional project + date | keyframe caption |

## Ranking beyond cosine (optional, later)

If clumping still bites after scoping, add:
- **MMR (maximal marginal relevance)** to diversify results away from
  near-duplicates.
- **Recency/chronology weighting** when the query is narrative-over-time.
- **Hybrid keyword + vector** (FTS5 alongside sqlite-vec) for proper nouns and
  exact phrases that embeddings blur.

Don't build these for v1. Ship exact cosine + filter-before-rank; add diversity/
hybrid only if retrieval quality demands it.

## Non-negotiable: retrieval returns IDs

Every retrieval result is a set of segment/clip IDs, which resolve to transcript
and timecodes in the DB. The LLM ranks and selects among *real* IDs; it never
conjures a match. Same pointer discipline, at the retrieval layer.
