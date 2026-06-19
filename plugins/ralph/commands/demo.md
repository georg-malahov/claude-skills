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
- a comment/section on the branch's PR linking that URL

## Step 0 — Capability probe (degrade, never hard-fail)

Resolve, in this order, and record what is available:

1. **ffmpeg + ffprobe** (`which ffmpeg ffprobe`) — required for mux. Missing → STOP and tell the user to install ffmpeg; nothing else can proceed.
2. **OpenAI TTS token** — `OPENAI_API_KEY` env, else `~/.config/video-skill/openai_token`. Missing → produce a **silent** demo (capture + subtitles + chapters, no voice) and say so.
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

## Step 3 — Generate narration (TTS)

```bash
<run_prefix> bun run <narration-script> tests/preview/<screenplay>.ts test-results/narration
```

Writes `test-results/narration/<id>.mp3` + `narration.json` (measured spoken durations). The output dir is a **sibling** of the Playwright capture `outputDir` so the per-run wipe does not delete the audio. Skip this step in silent mode.

## Step 4 — Paced capture

Run the demo capture spec against a running app, via `run_prefix`:

- Prefer a project script if present (`bun run preview:capture` / a `demo` script).
- Else run Playwright with the preview config: `<run_prefix> playwright test --config playwright.preview.config.* `.
- **Target app**: reuse what E2E uses — the warm dev server if one is up (single-mode `e2e: dev+prod`), otherwise a prod build served like the S3.5 gate. The capture is heavy (E2E-class); do not run it against the user's interactive dev session without confirming.

The spec reads `narration.json`, records each beat's `atMs`, performs the action, holds for the spoken duration + the pace tail, and writes `video.webm` + `test-results/preview/timing.json`.

## Step 5 — Build the demo

Write `demo-meta.json` — a `{title, description}` you generate from the plan + the narration transcript (a short "what this shows, by section" overview; this is the page's intro text). Then:

```bash
python3 <build-demo.py> test-results/preview/<video>.webm <out-dir> <video-skill-scripts-dir> \
  --narration-dir test-results/narration --meta demo-meta.json --lang <de|en|…>
```

Produces `video.mp4`, `video.vtt`, `metadata.json`, and (if the video-skill scripts resolved) the player `index.html` in `<out-dir>`.

## Step 6 — Host + attach to the PR

1. Upload with the video skill (credentials read from file, never passed as args):
   ```bash
   python3 <video-skill-scripts>/upload_s3.py <out-dir> --key=<feature-slug>-demo --credential-dir ~/.config/video-skill
   ```
   Capture the printed `[URL]`.
2. Find the branch's PR (`gh pr view --json url,number` on the current branch). If one exists, attach the demo:
   - Add a `🎬 Demo` line to the PR body (`gh pr edit --body`), or post a comment (`gh pr comment`) if editing the body is undesirable.
   - If no PR exists yet, print the URL and tell the user it will be attached when `/ralph pr` runs.
3. **Never** `git add` the video, audio, screenshots, or player page. Confirm `git status` shows only the screenplay/spec as changed.

## Invocation points

- **Standalone**: `/ralph demo` any time after a feature is built (a PR is optional — without one it just prints the hosted URL).
- **On execution completion**: `/ralph execute` S5 offers it (see `execute.md` → "Demo"). In autonomous mode (`RALPH_AUTO_PR`), it runs automatically after the PR is created so the link lands on the fresh PR — matching "demos generated automatically upon completion, before and after the PR".
- **From `/ralph pr`**: if a built demo exists for this branch (a hosted URL recorded this session), `pr` includes the link in the PR body.

## Session manifest

Create per dispatcher spec. `kind: demo`. `artifact:` → the screenplay file. Checkpoint after: screenplay drafted, narration generated, capture done, build done, hosted+attached. The capture/build steps are the slow ones — the manifest lets a re-invocation skip straight to hosting if the MP4 already exists.

## Constraints

- **No git bloat** — video/audio/screenshots/player page are hosted, only the screenplay + capture spec are committed.
- **Secrets from files, never args** — TTS token and S3 creds are read by the scripts via `--credential-dir` / env; never echo or pass them on the command line.
- **Capability-gated** — missing voice → silent demo; missing S3 → local only; missing harness → scaffold + stop. Never fail the run because a demo couldn't be produced; surface what was skipped.
- **Seeding in setup, not in the recorded timeline** — the single most common cause of dead air.
- **Heavy step** — capture is E2E-class. Don't auto-run it against the user's live dev session; use the E2E target.
