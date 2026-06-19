---
description: Auto-generate a narrated walkthrough video (screenplay → TTS → paced capture → mux), host on S3, attach to the PR.
argument-hint: '[plan-or-slug]   (defaults to the plan/diff this run delivered)'
---

# /ralph demo

Turn the change this run delivered into a **narrated, subtitled walkthrough video** and link it from the PR — the visual companion to the code review. The screenplay is the single source of truth: it is (re)drafted from the plan + `git diff`, voiced with TTS, captured at narration pace in a real browser, then muxed into an MP4 with a WebVTT subtitle track, scene chapters, and a player page hosted on S3.

**Artifacts are hosted, never committed** (no git bloat). The command only commits source: the screenplay + capture spec.

## What it produces

- `video.mp4` — HD screen capture with synced narration audio
- `video.vtt` — continuous subtitle track (matches the spoken lines)
- a player page (subtitles + chapter nav + download) at an S3 URL
- a comment/section on the branch's PR linking that URL (Desktop link is primary; Mobile link added as secondary when built)

Desktop is always built; Mobile is optional and only built after the desktop demo is done (it reuses the desktop narration, so it is cheap to add).

## Step 0 — Capability probe (degrade, never hard-fail)

Resolve, in this order, and record what is available:

1. **ffmpeg + ffprobe** (`which ffmpeg ffprobe`) — required for mux. Missing → STOP and tell the user to install ffmpeg; nothing else can proceed.
2. **OpenAI TTS token** — `OPENAI_API_KEY` env, else `~/.config/video-skill/openai_token`. **Missing → ask the user** (`AskUserQuestion`: "Provide an `OPENAI_API_KEY` now" *(Recommended)* / "Build a silent demo (no voice)"):
   - **They provide a key** → save it for this and future runs, then continue with TTS. Use the **same convention as the video skill's other credentials** (`deepgram_token` / `s3_credentials`): a single-line file in `~/.config/video-skill/` (persistent across plugin updates), read by the script internally, never passed as a CLI arg. Save with `mkdir -p ~/.config/video-skill && printf '%s' '<key>' > ~/.config/video-skill/openai_token && chmod 600 ~/.config/video-skill/openai_token`. Treat the key as a secret — write it to the file, never echo it back, never put it on a logged command line or in the progress file.
   - **They decline / aren't ready** → produce a **silent** demo (capture + subtitles + chapters, no voice) and say so. (`build-demo.py` handles the no-narration case; Step 4 is skipped.)
3. **S3 credentials** — `~/.config/video-skill/s3_credentials` (or the AWS_* env set the video skill reads). Missing → build locally, print the local path, skip hosting + PR attach.
4. **Playwright + capture harness** — a `playwright.preview.config.*` (or a `preview`/`demo` script in `package.json`) and a `tests/preview/*-demo.spec.*`. Missing harness → Step 1 scaffolds a starter and asks the user to flesh out the route navigation before a real capture.
5. **`run_prefix`** — reuse the `/ralph execute` probe's value if a session manifest with an `env:` block exists (host = empty, in-container = `bun run dx`). Otherwise infer the same way (a `dx` script / compose / `.claude/docker/` ⇒ `bun run dx`).
6. **video-skill scripts dir** — find `render_page.py` + `player.html` (the process-video plugin under `~/.claude/plugins/cache/*/process-video/*/skills/video/scripts`, or a path the user gives). Needed for the player page; without it, still produce the MP4 + VTT and skip the page.

State the resolved capabilities in one line before proceeding (e.g. "voice: on · host: S3 · harness: present").

## Step 1 — Resolve the harness (three-tier override chain)

- **Capture spec**: project `tests/preview/*-demo.spec.*`. If absent, scaffold one next to a copy of `${CLAUDE_PLUGIN_ROOT}/scripts/demo/screenplay.template.ts` and stop for the user to wire route navigation (a capture spec is inherently project-specific — it knows the routes, auth, and what to highlight).
- **Screenplay**: project `tests/preview/screenplay.*.ts` exporting `BEATS` (+ optional `NARRATION`). If absent, copy the template and continue — Step 2 fills in the beats.
- **Pipeline scripts** (prefer project override, else bundled):
  - narration: `scripts/preview/generate-narration.ts` → else `${CLAUDE_PLUGIN_ROOT}/scripts/demo/generate-narration.ts`
  - build: `scripts/preview/build-demo.py` → else `${CLAUDE_PLUGIN_ROOT}/scripts/demo/build-demo.py`

## Step 2 — Draft / refresh the screenplay from plan + diff

This is the model's job — the scripts are mechanical, the *narrative* is generated here.

1. Read the plan this run delivered (the `$ARGUMENTS` plan, else the most recent `docs/plans/completed/*.md`, else infer from `git log <default>..HEAD`).
2. Read `git diff <default>...HEAD --stat` and the key changed user-facing files to know **what is visibly new**.
3. (Re)write `BEATS` in the screenplay:
   - One beat per discrete thing the narrator says; ordered as a viewer would walk the feature.
   - Group beats into `scene`s (each becomes a chapter). 5–9 scenes is a good spread.
   - Keep `say` lines short and concrete — they double as the on-screen subtitle, verbatim.
   - Choose `pace` per beat (`emphasize` for headline moments, `compress` for connective tissue).
   - Preserve existing beat `id`s the capture spec already navigates; if you add/reorder beats, update the capture spec's beat references in the same commit.
4. **Seeding belongs in the capture spec's `beforeAll`/setup, never inline in a recorded beat** — inline data seeding shows as dead air in the final video. If the existing spec seeds inline, move it to setup as part of this step.
5. Commit the screenplay (+ any capture-spec beat-reference updates). The video/audio artifacts are NOT committed.

## Step 3 — Choose viewport(s)

Ask the user (via `AskUserQuestion`):

> **Which viewport(s) should this demo be built for?**
>
> 1. **Desktop only** *(Recommended — default)*
> 2. **Desktop + Mobile** — builds desktop first, then builds a mobile demo after, reusing the desktop narration (cheap to add).

In `RALPH_AUTO_PR` / non-interactive mode, **default to Desktop only** without prompting.

**Desktop is always built first and is the default.** Mobile is optional; it is only built after the desktop demo is finished. Record the choice (`VIEWPORTS=desktop` or `VIEWPORTS=desktop,mobile`) and proceed.

---

### DEMO_VIEWPORT convention

The project's `playwright.preview.config.ts` reads `DEMO_VIEWPORT=desktop|mobile` (default `desktop`) to pick the device preset, `video.size`, and — critically — to **suffix `outputDir`** so desktop and mobile captures land in separate directories and do not clobber each other across Playwright's per-run `outputDir` wipe:

- `test-results/preview-desktop/` — desktop capture + `timing.json`
- `test-results/preview-mobile/` — mobile capture + `timing.json`

The `test-results/narration/` directory is **viewport-independent** and never wiped by Playwright's `outputDir` rotation.

**Recommended `playwright.preview.config.ts` snippet** (projects own the actual file; this is the convention to implement):

```ts
// playwright.preview.config.ts
import { defineConfig, devices } from "@playwright/test";

const viewport = (process.env.DEMO_VIEWPORT ?? "desktop") as "desktop" | "mobile";

const deviceConfig =
  viewport === "mobile"
    ? { ...devices["iPhone 12"], viewport: { width: 390, height: 844 }, videoSize: { width: 390, height: 844 } }
    : { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, videoSize: { width: 1440, height: 900 } };

export default defineConfig({
  use: {
    ...deviceConfig,
    video: { mode: "on", size: deviceConfig.videoSize },
  },
  outputDir: `test-results/preview-${viewport}`,
  // … rest of config
});
```

The capture spec + config remain project-owned; the bundled scripts do not change.

---

## Step 4 — Generate narration (TTS) — runs ONCE, shared across viewports

```bash
<run_prefix> bun run <narration-script> tests/preview/<screenplay>.ts test-results/narration
```

Writes `test-results/narration/<id>.mp3` + `narration.json` (measured spoken durations). The output dir is a **sibling** of the Playwright capture `outputDir`s so the per-run wipe does not delete the audio. Skip this step in silent mode.

**Narration is viewport-independent.** Run this step exactly once regardless of how many viewports are being built. Mobile reuses the same `test-results/narration/narration.json` without re-running TTS.

## Step 5 — Per-viewport capture → build → host (desktop first)

Run this loop for each viewport in `VIEWPORTS` order (desktop first, mobile only if chosen and desktop succeeded):

### 5a — Paced capture

Set `DEMO_VIEWPORT=<viewport>` and run the demo capture spec against a running app, via `run_prefix`:

- Prefer a project script if present (`bun run preview:capture` / a `demo` script).
- Else run Playwright with the preview config: `DEMO_VIEWPORT=<viewport> <run_prefix> playwright test --config playwright.preview.config.*`.
- **Target app**: reuse what E2E uses — the warm dev server if one is up (single-mode `e2e: dev+prod`), otherwise a prod build served like the S3.5 gate. The capture is heavy (E2E-class); do not run it against the user's interactive dev session without confirming.

The spec reads `narration.json`, records each beat's `atMs`, performs the action, holds for the spoken duration + the pace tail, and writes `video.webm` + `test-results/preview-<viewport>/timing.json`.

### 5b — Build the demo

Write `demo-meta-<viewport>.json` — a `{title, description}` you generate from the plan + the narration transcript (a short "what this shows, by section" overview; this is the page's intro text). Append a viewport suffix to the title: **" (Desktop)"** or **" (Mobile)"**.

> **Note:** the `description` value is injected as **inline HTML** into the player page (a single `<div>`). It renders on one line — use it for a short overview, optionally with an `<a href>`. Escape literal `<` as `&lt;` and `&` as `&amp;` if the text is not intentionally HTML.

Then:

```bash
python3 <build-demo.py> test-results/preview-<viewport>/<video>.webm <out-dir>/<viewport> <video-skill-scripts-dir> \
  --timing test-results/preview-<viewport>/timing.json \
  --narration-dir test-results/narration \
  --meta demo-meta-<viewport>.json \
  --lang <de|en|…>
```

Produces `video.mp4`, `video.vtt`, `metadata.json`, and (if the video-skill scripts resolved) the player `index.html` in `<out-dir>/<viewport>`.

> **Note:** `build-demo.py` accepts `--timing`, `--narration-dir`, `--meta`, `--lang`, and the two positional args `video_in out_dir sk_dir`. No other flags.

### 5c — Host + record the URL

Upload with the video skill (credentials read from file, never passed as args):

```bash
python3 <video-skill-scripts>/upload_s3.py <out-dir>/<viewport> --key=<feature-slug>-demo-<viewport> --credential-dir ~/.config/video-skill
```

Capture the printed `[URL]` and record it as `DEMO_URL_<VIEWPORT>` for the PR attachment step.

If S3 credentials are absent, print the local path and skip hosting for this viewport.

### 5d — Mobile: only after desktop is done

If `VIEWPORTS=desktop,mobile`, **do not start the mobile loop until the desktop capture→build→host cycle has completed successfully.** If the desktop step fails, stop and report; do not attempt mobile.

## Step 6 — Attach to the PR

Find the branch's PR (`gh pr view --json url,number` on the current branch). If one exists:

- Add a `🎬 Demo` section to the PR body (`gh pr edit --body`), or post a comment (`gh pr comment`) if editing the body is undesirable.
- **Desktop link is primary.** If a mobile demo was also built, add it as a secondary line:
  ```
  🎬 Demo — [Desktop](<DEMO_URL_desktop>)  ·  [Mobile](<DEMO_URL_mobile>)
  ```
  If only desktop was built:
  ```
  🎬 Demo — [Desktop](<DEMO_URL_desktop>)
  ```
- If no PR exists yet, print the URL(s) and tell the user they will be attached when `/ralph pr` runs.

**Never** `git add` the video, audio, screenshots, or player page. Confirm `git status` shows only the screenplay/spec as changed.

## Invocation points

- **Standalone**: `/ralph demo` any time after a feature is built (a PR is optional — without one it just prints the hosted URL). You will be asked to choose Desktop only (default) or Desktop + Mobile.
- **On execution completion**: `/ralph execute` S5 offers it (see `execute.md` → "Demo"). In autonomous mode (`RALPH_AUTO_PR`), it runs automatically after the PR is created (Desktop only, no prompt) so the link lands on the fresh PR.
- **From `/ralph pr`**: if a built demo exists for this branch (a hosted URL recorded this session), `pr` includes the Desktop link (and Mobile link if built) in the PR body.

## Session manifest

Create per dispatcher spec. `kind: demo`. `artifact:` → the screenplay file. Checkpoint after: screenplay drafted, viewport chosen, narration generated, desktop-capture done, desktop-build done, desktop-hosted, (optional) mobile-capture done, mobile-build done, mobile-hosted, PR-attached. The capture/build steps are the slow ones — the manifest lets a re-invocation skip straight to hosting if the MP4 already exists for a given viewport.

## Constraints

- **No git bloat** — video/audio/screenshots/player page are hosted, only the screenplay + capture spec are committed.
- **Secrets from files, never args** — TTS token and S3 creds are read by the scripts via `--credential-dir` / env; never echo or pass them on the command line.
- **Capability-gated** — missing voice → silent demo; missing S3 → local only; missing harness → scaffold + stop. Never fail the run because a demo couldn't be produced; surface what was skipped.
- **Desktop first, mobile optional** — narration runs once and is shared. Mobile is only attempted after desktop succeeds. In non-interactive mode, default to Desktop only.
- **Seeding in setup, not in the recorded timeline** — the single most common cause of dead air.
- **Heavy step** — capture is E2E-class. Don't auto-run it against the user's live dev session; use the E2E target.
