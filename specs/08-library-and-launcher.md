# 08 — App, library, and launcher

Decided 2026-11. Three things, each with a single owner.

## The app vs. the library

**The app** is this repository: scripts, skill, launcher, specs. It is open
source (MIT), installs to `/Applications/Distaph`, and contains no user data.
It can be replaced, upgraded, or deleted without touching anything you own.

**The library** is yours: one folder (default `~/Distaph`) holding

| Path | What | Versioned? |
|---|---|---|
| `distaph.toml` | where your footage lives; model choices | yes |
| `vault/` | judgments — projects, narratives, review notes (Obsidian) | yes |
| `facts/*.jsonl` | clips, transcripts, keyframe captions, confirmed memberships | yes |
| `cuts/*.json` | cut lists (ID-only) | yes |
| `cuts/*.fcpxml` | timelines built from cut lists | no — rebuild |
| `db/archive.sqlite` | the working database | no — rebuild |
| `.claude/skills/distaph` | link to the installed skill | no — launcher recreates |

Footage stays on its drive and is never copied into either.

The library is located by `$DISTAPH_LIBRARY`, else the path written to
`~/.config/distaph/library` by `distaph init`, else `~/Distaph`. Relative paths
in `distaph.toml` resolve against the library folder.

### Why separate

- Code can be public while a life's worth of judgments stays private. One repo
  for both means every push risks publishing the vault.
- A `.app` must not hold data: writing into a bundle breaks its signature, and
  replacing the app would wipe the data.
- Upgrading the app is a `git pull` in `/Applications/Distaph`; the library
  doesn't move.

## Opinionated: your library is a git repository

`distaph init` creates the library as a git repo, and `sync` / `apply-review`
commit it after every run. Distaph **never pushes**. Whether the library leaves
the machine, and to where, is the user's decision — the README and site say
plainly that a remote should be private.

### Facts as text, not the database file

A SQLite file is a poor git citizen: binary, undiffable, and every commit
stores a full copy (embeddings alone reach hundreds of MB). So the database is
treated as a build artifact:

- **Versioned:** the expensive facts — transcripts above all, since they cost
  hours of Whisper — as sorted JSON Lines, one file per table. Deterministic
  output means a re-transcription shows up as a readable diff.
- **Not versioned:** embeddings (derived from text + a model name; rebuild in
  minutes) and the DB file itself.
- **Rebuild:** `distaph import-facts && distaph embed`.

`commit_library()` runs `export-facts` before each commit, so `facts/` never
drifts from the DB at a commit boundary.

## The launcher

The problem it solves is **recall**: remembering what the system can do, what
each command is called, and what arguments it takes. Slash commands don't fix
that — a flat list of everything still has to be scanned and translated from
intent. The launcher shows only Distaph's actions, in workflow order, with a
one-line explanation of each, and collects inputs by **browsing the library**
(pick a narrative or project from a list) rather than asking you to type slugs.

It is a launcher, not an editor. It renders a menu and reads the DB; it never
shows media, so it can't grow into a second Resolve or Obsidian.

Hybrid by kind of work:

- **Plumbing** (sync, apply review, find) runs the scripts directly and
  streams their output.
- **Judgment** (make a cut, work on a narrative, suggest ideas, talk) composes a
  prompt with the context filled in and hands off to Claude Code in the
  library, with the skill linked. When Claude Code exits, the menu returns.

Entry points: `Distaph.app` (built by `macos/build-app`, opens Terminal into
the menu), and `distaph` on the PATH (`distaph <command>` runs any script).
The `.app` and the CLI are the same program.
