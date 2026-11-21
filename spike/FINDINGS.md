# Resolve FCPXML round-trip spike — findings (2026-07-21)

Hand-written `spike-cut.fcpxml` (FCPXML 1.10) imported into Resolve Studio via
File → Import → Timeline, visually verified, exported back via File → Export →
Timeline. Import was clean; timeline read correctly (2 clips, 20s, portrait
1080×1920 @ 24).

## What survives exactly

- **Structure**: clip count, spine order, `offset` (timeline position) and
  `duration` of every clip — bit-exact after rational reduction
  (`240/24s` → `10/1s`, `12625/600s` → `505/24s`; same values).
- **Media paths**: `media-rep src` file URLs byte-identical, including the
  `%20`-escaped space. Relink keyed on absolute path — this is the stable
  join key back to the archive.
- **Sequence format**: resolution, frame rate, `tcStart`, total duration.
- Source in-point (`start`) for the same-rate clip: exact (`120/24s` → `5/1s`).

## What changes (tolerable, must be expected)

- **Export is a bundle**: Resolve writes `<name>.fcpxmld/Info.fcpxml`, not a
  bare `.fcpxml`. It *imports* bare `.fcpxml` fine. `build` emits bare files;
  anything that ever reads Resolve exports must handle both.
- **29.97 is re-declared as 30**: the NTSC format `1001/30000s` came back as
  `1/30s` (`FFVideoFormatRateUndefined`), and the mixed-rate clip's source
  in-point shifted `900900/30000s` → `901/30s` = **+3.3 ms** (sub-frame on a
  24fps timeline; frame = 41.7 ms). Round-trip validation needs a ±1-frame
  tolerance on source in-points of non-timeline-rate clips, not equality.
- **All identity except media path is rewritten**: resource IDs reassigned,
  event/project renamed `… (Resolve)`, and clip `name` attributes replaced by
  the media filename. ⇒ Clip names canNOT carry archive/segment IDs through
  Resolve. Media path (content-addressed archive path) is the only durable
  carrier, which is what the ID-only contract assumed.
- Cosmetic additions: `enabled`, `tcFormat`, `adjust-conform`,
  `adjust-transform` elements. Ignore on read.

## Contract for `build`

1. Emit bare FCPXML 1.10, rational times, absolute `file://` archive paths.
2. Express each clip's source `start`/`duration` in its native frame rate;
   expect Resolve to rationalize them.
3. Never encode meaning in clip/project names or resource IDs.
4. Mixed frame rates and portrait sequences are safe.
