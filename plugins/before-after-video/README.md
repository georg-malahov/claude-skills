# before-after-video

Proof for a pull request, on video: the base branch and the feature branch run
the same scripted scenario side by side, each labelled, with captions, a
circle on every tap and the numbers measured in that run. One MP4 that plays
on a phone, plus a before → after table to paste next to it.

```
«record a before/after video of the typing fix for the PR»
«сними видео до/после для этого PR»
```

Skill: `before-after-video` · Scripts: `skills/before-after-video/scripts/`.

It is a different genre from `/ralph:demo`, which narrates a walkthrough of
one version. Here two versions are compared, and the numbers carry the point.

## Install

Only this plugin:

```
/plugin marketplace add georg-malahov/claude-skills
/plugin install before-after-video@georg-malahov-claude-skills
```

Or as a bare skill, without the marketplace:

```bash
git clone --depth 1 https://github.com/georg-malahov/claude-skills /tmp/cs
cp -R /tmp/cs/plugins/before-after-video/skills/before-after-video ~/.claude/skills/
```

## Dependencies

| | |
|---|---|
| Node 18+ | runs the scripts |
| `playwright` + Chromium | recording, measuring (from the project, or `BA_NODE_PATH`) |
| `ffmpeg`, `ffprobe` | composing the MP4 |
| `sharp` (optional) | only for the fake camera |

```bash
brew install ffmpeg                                   # macOS
npm i --prefix ~/.cache/ba playwright sharp && npx --prefix ~/.cache/ba playwright install chromium
export BA_NODE_PATH=~/.cache/ba                       # when the project has no playwright
```

## How it works

```
serve-pair.mjs      before (main, :4101)  +  after (branch, :4102), both production builds
      │
screenplay.mjs      one scenario (scenario.mjs), run once per side, same conditions:
      │               badge · captions · tap circles · pinch · CPU throttle · fake camera
      │               instrument.js measures: long tasks, frame gaps, interactions, custom
      ├─ --no-video --runs 5  →  before.json / after.json  →  table.mjs  →  numbers.md
      └─ one recorded run     →  before.webm / after.webm  →  compose.mjs →  before-after.mp4
```

## Example

`examples/` holds a toy app in two versions (a filter whose ranking blocks the
main thread, then runs in a worker; a camera page that grabs the frame late,
then at the press) and two scenarios. `examples/run.sh` runs the whole
pipeline and prints:

| segment | metric | before (main) | after (this branch) | change | |
|---|---|---|---|---|---|
| typing | long-task time, ms | 2431 (2421–2542) | 0 (0–0) | −100% | better |
| typing | worst frame gap, ms | 1095 (1083–1142) | 9 (9–9) | −99% | better |
| typing | slowest interaction, ms | 1112 (1096–1152) | 24 (24–32) | −98% | better |
| typing | layout shift (CLS) | 0 (0–0) | 0 (0–0) | 0 | same |
| (whole run) | shutterLagMs | 467 | 0 | −100% | better (1 run) |

_Chromium, mobile 390×844, CPU ×4 (main thread only), 3 runs a side (shutter lag: 1 run)._

```bash
BA_NODE_PATH=~/.cache/ba bash plugins/before-after-video/skills/before-after-video/examples/run.sh
```

## Limits

- **Chromium only** for recording: CPU throttling, the touch pinch, long tasks
  and the fake camera all rely on Chromium. WebKit has no fake camera in
  Playwright — check Safari separately.
- **CPU throttling slows only the page's main thread.** Chromium refuses it
  for workers, so work moved into a worker runs at full speed under
  `--throttle` — the skill says so on the title card and in the table.
- Headless timings are not a phone's. They compare two builds on one machine
  under the same conditions; they do not predict absolute numbers on a device.
