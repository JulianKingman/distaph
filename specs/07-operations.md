# 07 — Operations & UX

How the system is actually used day to day. The design goal: few touchpoints,
everything else invisible. The scripts exist but you never run them
individually. *(Amended 2026-11: the launcher is now the front door, and the
app and library are separate — see `08-library-and-launcher.md`.)*

## The three surfaces

1. **The intake folder** (on the archive drive). Drop footage in. That is the
   entire ingestion UX. `sync` moves files into the content-addressed archive —
   **an empty intake folder means everything is cataloged.**
2. **Obsidian** (the vault, inside your library). Where you *read and confirm*:
   the review note (classification proposals, undated clips, possible dupes,
   repair proposals), narratives, project notes. Curation happens where the
   curated things live.
3. **The launcher** (`Distaph.app` / `distaph`). A menu of everything in
   workflow order; plumbing runs in place, judgment (cut, narrate, suggest)
   hands off to Claude Code with the skill loaded.

Day-to-day loop: drop files in intake → press **s** in the launcher →
skim the review note in Obsidian, tick boxes → press **a** → ask for
cuts when you want something made → import the FCPXML into Resolve.

## Storage layout

- **Media lives on an external drive**, never in the app or the library:
  - `/Volumes/<DRIVE>/intake/` — drop zone, emptied by ingest.
  - `/Volumes/<DRIVE>/archive/` — flat content-addressed store
    (`<hash-prefix>/<hash>.<ext>`). Files land here at ingest — the one
    sanctioned move, safe because nothing references a file until it is
    ingested — and never move again.
- **The app** (this repo: scripts, skill, launcher) lives in
  `/Applications/Distaph`. It holds no user data.
- **The library** (vault, facts, cuts, DB, `distaph.toml`) is the user's own
  folder and git repo — `~/Distaph` by default. See `08-library-and-launcher.md`.
- Paths are configured in the library's `distaph.toml`; scripts read it,
  nothing is hardcoded.

## Trigger model

`sync` is **launched by hand** (launcher, CLI, or by asking Claude) — not a watcher, not a cron. It is
idempotent (already-hashed content is skipped), so running it "too often" is
free. The long stages (Whisper, VLM captions) run in `sync`'s batch; kick it
off and walk away. A scheduled launchd wrapper can be added later without
changing anything — `sync` is already the single entry point.

**Drive not mounted → fail loudly and stop.** No partial runs, no silent
fallbacks, no "we'll catch it next time."

## Git & backup

- **Library auto-commits**: `sync` and `apply-review` each export text facts
  and end with one git commit of the library — a free audit trail of every
  judgment change and every transcript. Prose you edit by hand is picked up by
  the next auto-commit. Distaph never pushes.
- **The DB file is not in git**, but its expensive contents are: `facts/*.jsonl`
  rebuild it with `distaph import-facts`, then `distaph embed`.
- **Media backup is on you and matters most**: a lifetime of footage on a
  single external drive is a single point of failure. Backblaze Personal
  (covers external drives) or a second cloned HDD. The system does not manage
  this; it just depends on it.
