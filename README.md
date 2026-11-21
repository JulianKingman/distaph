<p align="center"><img src="assets/icon/distaph-tile-180.png" width="120" alt="Distaph icon"></p>

# Distaph

**Spin a lifetime of raw footage into stories.**

A distaff holds the raw fiber while you draw it out and twist it into one
thread. Distaph does that for video: it holds everything you've ever recorded,
lets you draw out the moments that matter across years and projects, and spins
them into rough cuts that open in DaVinci Resolve.

It's open source, runs on your Mac, and keeps your footage and your judgments
in files you own.

→ [distaph.com](https://distaph.com)

## What makes it different

- **Narratives outlive videos.** A narrative is a named, ordered thread of real
  moments that keeps growing across years. One narrative can become many
  videos; one video can draw on many narratives.
- **It can't make things up.** The AI chooses and orders *pointers* to real
  transcript segments. A validator checks every pointer against the database
  before anything reaches a timeline, so a cut can't contain a line you never
  said.
- **Facts and judgments are kept apart.** Transcripts, timecodes and
  embeddings are regenerable facts. Project membership, narrative order and
  taste are your judgments, kept as markdown you edit in Obsidian. Either can
  be rebuilt without losing the other.
- **Your library is a git repository.** Every sync and review is a commit.
  Transcripts are versioned as text, so the database is a build artifact.
- **Local by default.** Whisper, captioning and embeddings run on Apple
  Silicon via MLX. Footage never leaves your drive.

## How it works

1. **Drop footage** in your intake folder.
2. **Sync.** Distaph files it by content hash, dates it from metadata,
   transcribes it, captions keyframes and embeds everything.
3. **Review in Obsidian.** Proposed project tags, undated clips and possible
   duplicates arrive as a checklist. Tick what you agree with; apply.
4. **Make something.** Describe a video, or start from a narrative. Claude
   picks and orders real segments; Distaph validates them and builds an
   FCPXML.
5. **Finish in Resolve.**

## Install

Requirements: an Apple Silicon Mac, Xcode (to build the app),
[uv](https://docs.astral.sh/uv/), `ffmpeg`, [Claude Code](https://claude.com/claude-code) for the judgment
features, and DaVinci Resolve (Studio recommended) for finishing.

```sh
git clone https://github.com/JulianKingman/distaph /Applications/Distaph
/Applications/Distaph/macos/build-app     # builds Distaph.app with Xcode, links `distaph`
```

Open **Distaph** from Spotlight or Launchpad. The first time, it asks you to
choose a library folder or create one (`~/Distaph` is a good default), then
opens your settings so you can point it at your footage drive. Hold **Option**
while opening Distaph to switch libraries later.

You can also build the app by opening `macos/Distaph/Distaph.xcodeproj` and
pressing Run. Either way it lands in `/Applications/Distaph/Distaph.app`.

## The launcher

Open Distaph and you get a menu of everything it does, in the order you'd do
it. Nothing to memorize.

| Key | Action | |
|---|---|---|
| s | Sync new footage | runs locally |
| r | Review in Obsidian | opens the review note |
| a | Apply review | runs locally |
| f | Find footage | semantic search across every clip |
| c | Make a cut… | hands off to Claude Code |
| n | Work on a narrative… | hands off to Claude Code |
| i | Suggest ideas | hands off to Claude Code (early) |
| t | Talk to Claude | Claude Code in your library |

Every action is also a command: `distaph sync`, `distaph search "…"`,
`distaph build cuts/x.json --fcpxml cuts/x.fcpxml`, and so on.
`distaph --help` lists them.

## Your library

```
~/Distaph/
├── distaph.toml   where your footage lives
├── vault/         your judgments — open in Obsidian
├── facts/         transcripts and metadata as text (versioned)
├── cuts/          cut lists (versioned) and built timelines (not)
└── db/            working database (not versioned; rebuildable)
```

Distaph commits this folder after every sync and review, and never pushes. If
you add a remote, make it private: it's a record of your life.

Rebuild the database on a new machine with
`distaph import-facts && distaph embed`.

## Status

Early and opinionated. Working today: ingest, dating, local transcription,
keyframe captioning, embeddings, semantic search, the review flow, validated
cuts with picture-in-picture, FCPXML export to Resolve, and the launcher.
Next: multi-level summaries, narrative tooling, and idea suggestions drawn from
the whole archive. The design lives in [`specs/`](specs/).

## Development

```sh
uv run --python 3.13 --with pytest pytest tests/
```

Tests use tiny synthetic clips generated with ffmpeg and stub models, so they
run anywhere in under a minute.

## License

MIT
