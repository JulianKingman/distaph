# My Distaph library

This folder is mine, not the app's. It holds everything Distaph knows about my
footage. The footage itself stays on its drive.

- `distaph.toml` — where my footage lives and which local models to use.
- `vault/` — my judgments: projects, narratives, review notes. Open it in Obsidian.
- `facts/` — transcripts, captions and clip metadata as text. Regenerable, but
  expensive to regenerate, so it's versioned.
- `cuts/` — cut lists (`*.json`). Timelines built from them aren't versioned.
- `db/` — the working database. Not versioned; rebuild it with
  `distaph import-facts && distaph embed`.

Distaph commits this repository after every sync and review. It never pushes.
If you add a remote, keep it private: this is a record of your life.
