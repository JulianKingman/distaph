# Backlog — driven by review feedback

Feedback from real cut reviews lands here with a disposition, so it shapes
tooling defaults, the skill's editorial rules, or a fix — and doesn't evaporate.

## From the first narrative cut review (2026-07-25, first narrative test cut)

1. **Cuts are too tight; sentences nearly clipped.** → `build` gains breathing
   room: pad each segment (default ~0.25s in/out), clamped to clip bounds and,
   later, snapped to word-timing gaps (words_json exists for exactly this).
   Tooling default, not per-cut fiddling.
2. **Some selected segments should be dropped (e.g. an off-topic aside).** →
   Editorial selection taste. Belongs to the skill's `cut` operation when it
   exists; until then, cut JSON is hand-editable — delete the line, rebuild.
   Accumulate taste rules in `vault/editorial-notes.md` (human-owned; the
   skill reads it when selecting): first entry — trim asides that break the
   through-line unless they're the ending beat.
3. **PiP connected clip doesn't appear at all in Resolve.** → Bug/dialect
   mismatch. Next step mirrors the original spike method: build a tiny PiP
   manually in Resolve, export FCPXML, diff against what `build` emits, adopt
   Resolve's own shape. Do not guess variants blind.
4. **Audio needs a noise pass.** → Never modify archive originals (facts are
   immutable). Options at edit/render time: Resolve Studio Voice Isolation
   (manual toggle today; scriptable once `--push` exists), or derived
   denoised proxies (ffmpeg arnndn) stored as new derived files if manual
   toggling gets old. Decide when it hurts.
5. **The system should suggest connective material** — lines to record, or
   existing clips/B-roll that tie the narrative together. → This is the
   skill layer: keyframe/summary search supplies real candidates (IDs);
   proposed *words to say* are prose suggestions, clearly not footage claims
   (the ID contract already draws this line). Feeds `cut`/`narrate`/`suggest`
   op design in SKILL.md.

## Process

After each review session: notes get dispositioned into (a) tooling defaults,
(b) editorial-taste rules the skill will read, or (c) bugs/spikes — in this
file, until `sync`/SKILL.md give judgments their proper vault home.
