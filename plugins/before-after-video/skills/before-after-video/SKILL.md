---
name: before-after-video
description: >
  Record a before/after comparison video of a web UI change as proof for a PR:
  the base branch (main) and the feature branch run side by side in the same
  scripted scenario, with labels, captions, visible taps and numbers measured
  in the run (long tasks, frame stalls, interaction latency, custom metrics,
  camera shutter lag), composed into a phone-friendly MP4 plus a before → after
  table. Use for performance fixes, UX changes and regressions. Triggers on:
  "before/after video", "side-by-side video", "show the difference in the PR",
  "prove it's faster", "compare main vs branch on video", "видео до/после",
  "сравнение до и после", "покажи разницу на видео", "докажи в PR".
argument-hint: "[what the change claims, e.g. 'typing no longer freezes the list']"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - AskUserQuestion
---

# before-after-video — main vs the branch, side by side, measured

One scripted scenario runs against two production builds — `before` (main)
and `after` (this branch) — in the same browser under the same conditions.
Each run is recorded with a side badge, captions, a circle on every tap and
numbers measured in that very run. The recordings are composed into one MP4
(side by side, or a 2×2 grid for two scenarios), and repeated runs without
recording give the before → after table that goes next to the video.

This is not `/ralph:demo`: that is a narrated walkthrough of **one** version.
This is a comparison of **two**, and the numbers are the point.

## When to use

- A performance fix: jank, long tasks, slow input, slow first result.
- A UX change whose effect is easier to see than to describe.
- A regression — show it on main and gone on the branch (or the reverse).
- A camera flow: shutter lag, a steadier viewfinder (fake camera, below).

Do not use it when the difference is a static screenshot's worth, or when no
number or visible behaviour actually changes — say so instead.

## Scripts

```bash
BA=""
for c in "${CLAUDE_PLUGIN_ROOT:-/nonexistent}/skills/before-after-video/scripts" \
         "$HOME/.claude/skills/before-after-video/scripts" \
         $(ls -d "$HOME"/.claude/plugins/cache/*/before-after-video/*/skills/before-after-video/scripts 2>/dev/null | sort -r); do
  [ -f "$c/screenplay.mjs" ] && BA="$c" && break
done
[ -n "$BA" ] || { echo "before-after-video scripts not found"; exit 1; }
```

| file | what it does |
|---|---|
| `serve-pair.mjs` | starts the before and after servers on two ports, waits until both answer, runs a command against them (`BEFORE_URL`, `AFTER_URL`), stops both; refuses a port that is already taken |
| `scenario.template.mjs` | the scenario to copy and edit: `SCENARIO = { path, async run(page, h) }` |
| `screenplay.mjs` | the harness: runs a scenario on one side — presets, badge, captions, tap circles, pinch, CPU throttling, fake camera, measuring — and writes `<side>.webm` + `<side>.json` |
| `instrument.js` | injected before the page: long tasks, rAF frame gaps, interaction latency, layout shift, custom metrics, optional worker-message hook. Observes only, never changes behaviour |
| `fake-camera.mjs` | any image → a looping `.mjpeg` for Chromium's fake camera: shaking in a hand, sliding or still, with the frame number burned into a code bar |
| `frame-code.js` | reads that frame number back in the page — from the `<video>`, a canvas, a bitmap or the photo `Blob` |
| `compose.mjs` | ffmpeg: side by side, stacked or 2×2, aligned on a mark, optional title card, H.264 yuv420p faststart MP4, stills to check |
| `table.mjs` | the before → after Markdown table from the JSONs, median and range over runs, with a verdict that says "no clear change" when the ranges overlap |
| `../examples/` | a toy app in two versions, two scenarios and `run.sh` — the whole pipeline end to end |

Run the scripts **from the project root** so they use the project's own
`playwright` (and `sharp` for the fake camera). If the project has neither,
install them once outside it and point `BA_NODE_PATH` at that folder:

```bash
npm i --prefix ~/.cache/ba playwright sharp && npx --prefix ~/.cache/ba playwright install chromium
export BA_NODE_PATH=~/.cache/ba
```

Also needed: Node 18+ and `ffmpeg`/`ffprobe` on the PATH.

## Workflow

Keep everything this produces out of the project: work in the scratchpad (or
`${TMPDIR:-/tmp}`), call it `$W` below. Nothing here is committed to the project.

### 1. Pin down the claim

What does the PR claim, in one sentence per claim? Each claim becomes one
scenario (one row of the video) and one or two metrics:

| claim | measure with |
|---|---|
| typing / scrolling no longer freezes | `h.measure` → `longTaskMs`, `frameGapMax`, `stalls` |
| a tap answers faster | `interactionMax`, or `h.metric` from the moment the result appears |
| the result shows up sooner | `h.metric("resultMs", …)` timed in the page |
| the photo is the frame you saw | fake camera + `frame-code.js` → `shutterLagMs` |
| the layout no longer jumps | `cls` |

If the effect only shows on a slow phone, plan a CPU throttle (step 5).

### 2. Two production builds

`before` is the base the branch will merge into — the merge base, so the only
difference is this branch's diff (plain `main` if the user asks for that):

```bash
BASE=$(git merge-base HEAD origin/main)
git worktree add "$W/before" "$BASE"
```

Install and build both **the same way, in production mode** (`build` + `start`,
not a dev server — dev builds are slower and uneven). Same `.env`, same API or
database, same feature flags. Then start both:

```bash
node "$BA/serve-pair.mjs" \
  --before "npm run start -- -p \$PORT" --before-cwd "$W/before" --before-port 4101 \
  --after  "npm run start -- -p \$PORT" --after-cwd  .           --after-port  4102 \
  --path / --logs "$W/logs"
```

Leave it running in the background, or append `-- <command>` to run one
command against both and stop them afterwards. Each command gets `PORT`.

### 3. Write the scenario

```bash
mkdir -p "$W" && cp "$BA/scenario.template.mjs" "$W/scenario.mjs"
```

Edit `SCENARIO.run`: the few steps that show the change, a caption before
each, the measured number in a caption after it, a `h.mark("ready")` once the
app is usable. Read the template's header — the helper `h` is documented
there. The same code runs on both sides: **never branch on the side.**

### 4. Smoke run, no video

```bash
node "$BA/screenplay.mjs" --scenario "$W/scenario.mjs" --side before --url http://localhost:4101 --out "$W/smoke" --no-video
node "$BA/screenplay.mjs" --scenario "$W/scenario.mjs" --side after  --url http://localhost:4102 --out "$W/smoke" --no-video
```

Both must pass without page errors (they are printed, and kept in the JSON).
A failing run with video keeps `<side>.failed.webm` — watch it.

### 5. Measure — repeated runs, no video

Recording costs CPU; numbers come from runs without it. Five runs a side is a
good default; interleave the sides so drift in the machine hits both:

```bash
for i in 1 2 3 4 5; do for s in before after; do
  node "$BA/screenplay.mjs" --scenario "$W/scenario.mjs" --side $s --url http://localhost:$([ $s = before ] && echo 4101 || echo 4102) \
    --out "$W/runs/$i" --no-video --throttle 4
done; done
```

or simply `--runs 5 --no-video` per side (one JSON with five runs). Then:

```bash
node "$BA/table.mjs" "$W"/runs/*/before.json "$W"/runs/*/after.json
```

`table.mjs` takes any number of JSONs, groups them by side and pools their
runs. It warns if the runs were not made under the same conditions.

### 6. Record — one run a side, same flags

```bash
for s in before after; do
  node "$BA/screenplay.mjs" --scenario "$W/scenario.mjs" --side $s \
    --url http://localhost:$([ $s = before ] && echo 4101 || echo 4102) --out "$W/rec" --throttle 4
done
```

Useful flags: `--preset desktop` (1280×800) or the default `mobile` (390×844,
touch, DPR 2, Android Chrome UA) · `--lang ru` (ДО — main / ПОСЛЕ — эта ветка)
· `--label` · `--hud` (a live readout of long tasks and the worst frame in a
corner) · `--caption-pos top` · `--badge-pos top-left` · `--camera clip.mjpeg`.

### 7. Compose and look at it

```bash
node "$BA/compose.mjs" --out "$W/before-after.mp4" --align ready --frames 6 \
  --title "Typing no longer freezes the list" --subtitle "Same keystrokes, same pace, both builds" \
  "$W/rec/before.webm" "$W/rec/after.webm"
```

Two inputs → side by side; four → a 2×2 grid, rows = scenarios, columns =
before/after (pass them in that order). `--layout vstack` suits wide desktop
recordings on a phone. The title card lists the badges and the conditions
(preset, viewport, CPU throttling, fake camera) read from the JSONs.

**Open the stills** (`before-after-frames/*.png`) with Read before handing
anything over: both badges readable, captions not covering what matters,
taps visible, the two sides in step, nothing cut off. Fix and re-record if not.

### 8. Report

Put the numbers next to the video. In the PR:

```markdown
## Before → after

<the video — see "Delivering the video">

| segment | metric | before (main) | after (this branch) | change | |
|---|---|---|---|---|---|
| typing | worst frame gap, ms | 1095 (1083–1142) | 9 (9–9) | −99% | better |
| typing | slowest interaction, ms | 1112 (1096–1152) | 24 (24–32) | −98% | better |

Chromium, mobile 390×844, CPU ×4 (main thread only), 5 runs a side, median (min–max).
Not improved: first load (1.9 s → 1.9 s) — this change does not touch it.
```

## Identical conditions — the checklist

- **Same scenario code** on both sides, no side-dependent branches.
- **Same data**: the same seed, fixtures, account and backend. A fresh browser
  context per run (the harness does this), so no cookies or storage carry over.
- **Same cache state**: both cold (the default) or both warmed the same way.
- **Same viewport, device preset, locale, timezone, colour scheme** — the
  harness fixes them per run (`--locale`, `--timezone`, `--color-scheme`).
- **Same CPU throttle.** `Emulation.setCPUThrottlingRate` slows **only the
  page's main thread**: Chromium answers "Operation is only supported for
  pages, not workers" for a worker, so a worker runs at full speed. If the
  change moves work into a worker, the throttled comparison flatters the
  after side — say so, or compare unthrottled, or on a real slow phone.
  GPU and network are not throttled either.
- **Same machine, one side at a time.** Never record both sides at once; close
  other heavy work; interleave repeated runs.
- **Same fake camera clip** for camera scenarios.

## Honesty rules

- **Never fake a number.** Every number in a caption, a title or the table
  comes from `h.measure` / `h.metric` / the JSONs of these runs. No typed-in
  values, no numbers from another machine.
- **Label everything.** Each side carries its badge in every frame; the title
  card and the PR state the conditions, including the throttle and what it
  does not cover.
- **Show where there is no gain.** Report metrics that did not move or got
  worse. `table.mjs` prints "≈ no clear change" when run ranges overlap —
  keep those rows. A regression elsewhere belongs in the report too.
- **Do not cherry-pick.** The table is the median of all runs with the range;
  the video is one ordinary run, not the best of twenty.
- **Do not edit time.** `compose.mjs` only trims both inputs at the start to
  the same mark and freezes the shorter one at its end. No speed changes, no
  cuts in the middle, no per-side offsets.
- **If the scenarios had to differ** (the after build has a button the before
  build lacks), say it in the captions and the PR.

## Fake camera (Chromium only)

```bash
node "$BA/fake-camera.mjs" --image sheet.jpg --out "$W/cam.mjpeg" --motion shake   # or slide / still
node "$BA/screenplay.mjs" … --camera "$W/cam.mjpeg"
```

Chromium plays the clip as the camera (30 fps, looped) through
`--use-fake-ui-for-media-stream --use-fake-device-for-media-stream
--use-file-for-fake-video-capture=…`; the harness adds these and injects
`frame-code.js`. Every frame carries its number (0 … N−1) in a white bar with
a 10-bit code. In the page, `__frameCode.read(videoEl)` is the frame on screen,
`await __frameCode.readBlob(photo)` the frame in the photo; shutter lag =
`((shot − down) mod N) × 1000/30` ms. See `examples/camera.scenario.mjs`.

**WebKit has no fake camera** through Playwright (no file-backed capture, and
the CDP pieces — throttling, touch pinch, long tasks — are Chromium-only).
Record camera and performance videos in Chromium; check WebKit / iOS Safari
separately. Stubbing `getUserMedia` with a canvas `captureStream()` works in
WebKit but replaces the real capture path — label such a video as a stub.

## Delivering the video

- The MP4 is H.264 High, yuv420p, `+faststart`, even dimensions — it plays in
  every phone browser, Telegram and GitHub. `compose.mjs` warns over 10 MB
  (GitHub's limit for videos on free plans): raise `--crf` or lower
  `--max-width`.
- **To the user now**: send the file (in the Claude desktop app with
  SendUserFile; otherwise print the path).
- **Into the PR**: `gh` cannot attach videos. Either the user drags the MP4
  into the PR description or a comment in the browser (GitHub turns it into
  an inline player), or it is hosted — e.g. the `process-video` plugin's
  `/video` share or its S3 upload — and linked. Paste the table as text next
  to it.
- **Never commit** the video, the stills or the `.mjpeg` to the project.

## Troubleshooting

| symptom | cause / fix |
|---|---|
| `port 4101 (before) already has a server on it` | an old server; stop it — otherwise it would be measured instead of your build |
| `Cannot find playwright` | run from the project root, or set `BA_NODE_PATH` |
| a tap times out: "… intercepts pointer events" | something covers the target — often a pinch that zoomed the page; wait for the state, or tap coordinates |
| `__frameCode.read` returns −1 | no code visible: the camera has not started yet, or the source is cropped — read the `<video>` element, not a screenshot |
| both sides look the same | check the ports really serve different builds (`git -C "$W/before" log -1`), and that the throttle flag reached the harness (in zsh an unquoted `$flags` is one argument) |
| the numbers swing between runs | more runs, fewer background apps; report the range |
