# Finalise /ralph demo + port hardened preflight + retire screenshots + 0.4.1

## Overview
One coherent finalisation pass on the `ralph` plugin (touching `dev-workflow` for the
screenshot retirement), shipped as a consistent **0.4.1** bump. Delivers four things:

1. **Retire screenshots; delete `/preview-check`.** The narrated `/ralph demo` video is now
   the canonical PR visual. Remove every screenshot reference and delete the `/preview-check`
   command outright.
2. **Port the hardened execute preflight** (deps/repo-health probe) that was only ever in the
   installed cache, and **extend it with E2E-runtime readiness** that attempts the project's
   documented `bun run up` before degrading; and **record E2E timings in the post-review prod
   gate** so the suite's shard balance stays fresh as specs are added.
3. **Add a desktop/mobile viewport step to `/ralph demo`.** Desktop is the default and always
   built first; mobile is optional and built after desktop is ready, reusing the desktop
   narration so it's cheap to add.
4. **Demo polish + version consistency.** Fix the silent-mode `build-demo.py` crash, note the
   HTML-description behaviour, and bump + sync `plugin.json` / `marketplace.json` / READMEs.

## Context

### Repo shape (matters for validation)
This is the **plugin-source** repo (`claude-skills`): pure markdown + python + ts plugin
files, **no `package.json`, no lint/typecheck/unit/E2E harness**. So `/ralph execute`'s probe
will resolve `e2e: unsupported` and there is no `bun run lint`. "Validation" here is **static**:
JSON validity (`marketplace.json`, each `plugin.json`), `python3 -m py_compile` for
`build-demo.py`, a `bun`/`tsc`-parse of the demo `.ts` scripts if bun is present, and
**grep sweeps for dangling references**. The changes here describe behaviour for *other* repos
that install the plugin; they cannot be runtime-tested from here.

### Thread B — the hardened preflight (the important correctness fix)
`plugins/ralph/commands/execute.md` step 2 ("Dependencies ready?") is the **naive** version:
it trusts `bun run lint` / `--version` / a `node_modules/.bin` listing. Those **all pass on a
broken dependency graph**, so they are not readiness signals. The hardened version lives only
in the installed cache (`~/.claude/plugins/cache/.../ralph/0.3.0/commands/execute.md`, edited
2026-06-18, the day after the repo's 0.3.0 commit); `git log -S` confirms it never entered repo
history. Port it verbatim, then extend to E2E-runtime readiness.

Hardened step-2 (verbatim source to port) adds: parse `package.json` deps+devDeps and confirm
each resolves under `node_modules` (host-native worktree, or in-container via `run_prefix`);
lockfile-vs-install staleness as a signal; run `typecheck`(TS2307)/`test:unit` as the
*authoritative* module-resolving probe when present; three remediation paths (host installer /
Docker volume `bun run up` / Docker-baked-image needing a rebuild); HARD-STOP calibrated to what
the project actually supports (never block a script-light repo, never green-light on `lint` alone).

### Thread A — screenshot references to remove (full surface)
- `plugins/dev-workflow/commands/preview-check.md` — **delete the file**
- `plugins/ralph/commands/pr.md:79` — Screenshots line
- `plugins/ralph/commands/review.md:34` — surfaces /preview-check screenshots inline
- `plugins/dev-workflow/commands/orchestrate.md:219` — checklist "Invoke /preview-check"
- `plugins/dev-workflow/commands/create-pr.md:86` — references the report
- `plugins/dev-workflow/README.md:12` — table row
- `plugins/dev-workflow/.claude-plugin/plugin.json` — description "visual preview sanity checks"
- root `README.md:19` — dev-workflow row mentions /preview-check + "visual sanity checks"
- `.claude-plugin/marketplace.json` — dev-workflow description "visual sanity checks"

### Viewport feature mechanics (how desktop/mobile works)
The capture is driven by a project-owned `playwright.preview.config.ts` whose `use` block sets
`viewport`, `video.size`, and `outputDir`; the spec always writes `<outputDir>/timing.json`.
Narration (TTS audio in `test-results/narration/`) is **viewport-independent**, so:
- **Convention:** demo capture reads `DEMO_VIEWPORT=desktop|mobile` (default `desktop`). The
  project's preview config uses it to pick device + `video.size` AND to suffix `outputDir`
  (`test-results/preview-<viewport>`) so desktop/mobile captures don't clobber each other
  across Playwright's per-run `outputDir` wipe. demo.md documents this + ships a recommended
  config snippet (projects own the actual config + spec).
- **Flow:** narration runs once (shared). Then capture→build→host runs **desktop first**, and
  **mobile only after desktop is done**, reusing the same `narration.json` (audio) with mobile's
  own `timing.json`. Each viewport gets its own out-dir, S3 key (`<slug>-demo-desktop` /
  `-demo-mobile`), and `demo-meta.json` title suffix. No `build-demo.py` flag change is needed —
  demo.md passes the per-viewport `--timing` path + out-dir + `--meta`.
- PR attach: Desktop link is primary; Mobile link added as secondary when built.

### Constraints / principles
- **Generic, capability-detected** — parameterise for the standard T3 + ZenStack + Better Auth
  template (runner name, run_prefix, Docker shape, sidecar set); no hardcoded project paths.
  Capability detection over user-facing mode menus; verify by probing before acting.
- **Host-side deps only** — preflight auto-install runs on the host, never an agent mid-run.
- **marketplace.json is the install source-of-truth** — must move with plugin.json.
- Demo/screenshot artifacts hosted, never committed.

## Development Approach
- **No app/test harness in this repo** — `/ralph execute`'s probe resolves `e2e: unsupported`;
  there is no per-task dev E2E and no prod E2E gate. Do not author `FIXME(e2e)` placeholders for
  documentation tasks.
- **Per-task validation = static checks** appropriate to the file touched:
  - JSON files → parse with `python3 -c 'import json,sys; json.load(open(f))'`.
  - `build-demo.py` → `python3 -m py_compile`.
  - demo `.ts` scripts → `bun build --no-bundle` / `tsc --noEmit` only if a toolchain is present; else skip.
  - Doc edits → targeted `grep` proving no dangling references remain.
- **Commit per task** with a clear message; this repo's "green" is "static checks pass + no
  dangling refs", not a lint/unit suite.
- TDD/unit tests: **N/A** (no code under test); the one behavioural script change (silent-mode
  guard) is verified by a manual `build-demo.py` dry-run reasoning + py_compile, since there is
  no test runner here.

## Implementation Steps

### Task 1: Port + extend the hardened execute preflight
- [x] Replace `execute.md` step 2 ("Dependencies ready?") with the hardened cache-0.3.0 text:
      deps-resolve sanity check (package.json deps+devDeps vs node_modules, host or via
      run_prefix), lockfile staleness signal, `typecheck`/`test:unit` as authoritative probe
      when present, three remediation paths, calibrated HARD-STOP.
- [x] Extend E2E capability (step 3 / new "3c — E2E-runtime readiness"): when `e2e != unsupported`,
      before declaring runnable, **attempt the project's documented start (`bun run up` or
      equivalent) once**, then verify Docker daemon responsive (`docker info`) and declared
      sidecars (DB / GreenMail-mail / compose services) reachable; if still not ready, **degrade
      `e2e` to not-runnable** (record in `env:`) rather than failing late in S3.5. Reuse the 3b
      "host-orchestrating entrypoint" classification — do not double-launch sidecars the
      `test:e2e` entrypoint already owns.
- [x] Keep it generic (detect, don't hardcode); mirror the deps "attempt once, then re-verify" policy.
- [x] Static check: re-read the edited section for internal consistency with `env:` block,
      S3.5, and resume (which re-verifies readiness). Grep that `e2e_cmd` / `env:` references still line up.

### Task 2: Retire screenshots and delete /preview-check
- [x] Delete `plugins/dev-workflow/commands/preview-check.md`.
- [x] Remove the Screenshots line from `plugins/ralph/commands/pr.md` (keep the Demo line).
- [x] Remove the /preview-check screenshot surfacing from `plugins/ralph/commands/review.md`.
- [x] Remove the "Invoke /preview-check" checklist item from `plugins/dev-workflow/commands/orchestrate.md`.
- [x] Remove the report reference from `plugins/dev-workflow/commands/create-pr.md`.
- [x] Update `plugins/dev-workflow/README.md` (drop the row) and `plugins/dev-workflow/.claude-plugin/plugin.json` description (drop "visual preview sanity checks").
- [x] Static check: `grep -rn "preview-check\|docs/previews" plugins/ README.md .claude-plugin/` returns **zero** hits.

### Task 3: Add the desktop/mobile viewport step to /ralph demo
- [x] Add a viewport-selection step to `plugins/ralph/commands/demo.md` (after the capability
      probe / harness resolve, before capture): AskUserQuestion — "Desktop only" (Recommended,
      default) / "Desktop + Mobile". In RALPH_AUTO_PR / non-interactive mode default to Desktop only.
- [x] Restructure Steps 4–6 into a **per-viewport loop, desktop first**: narration (Step 3) runs
      once and is shared; then capture→build→host desktop; then, only if "both" and desktop
      succeeded, capture→build→host mobile reusing the same `narration.json`.
- [x] Document the `DEMO_VIEWPORT=desktop|mobile` convention (device + `video.size` + suffixed
      `outputDir`) and include a recommended `playwright.preview.config.ts` snippet so projects
      wire the switch; note the spec/config remain project-owned.
- [x] Per-viewport hosting: distinct out-dir + S3 key (`<slug>-demo-desktop` / `-demo-mobile`)
      + `demo-meta.json` title suffix (Desktop/Mobile). PR attach: Desktop primary, Mobile secondary.
- [x] Static check: re-read demo.md end-to-end for flow coherence (narration-once, desktop-first,
      mobile-optional-after); confirm no `build-demo.py` flag is referenced that doesn't exist.

### Task 4: Demo polish — silent-mode guard + HTML-description note
- [x] `plugins/ralph/scripts/demo/build-demo.py`: guard missing/empty `narration.json` — when
      absent or `beats` empty, **skip the audio mux** (no `amix=inputs=0`) and transcode
      `webm→mp4` directly; VTT + chapters + page still build from `timing.json`.
- [x] `plugins/ralph/commands/demo.md` Step 5: note that the `demo-meta.json` description is
      injected as **inline HTML** (single line; escape `<`/`&` if literal text is intended).
- [x] Static check: `python3 -m py_compile build-demo.py`; reason through the silent path
      (no narration dir → builds MP4 + VTT + chapters, no crash).

### Task 5: Version bump + consistency sync (0.4.1)
- [ ] `plugins/ralph/.claude-plugin/plugin.json`: 0.4.0 → **0.4.1**.
- [ ] `plugins/dev-workflow/.claude-plugin/plugin.json`: 0.1.0 → **0.1.1** (touched by Task 2).
- [ ] `.claude-plugin/marketplace.json`: ralph `version` 0.3.0 → **0.4.1** + refresh description
      (add demo) + keywords (add `demo`); dev-workflow 0.1.0 → **0.1.1** + description (drop
      preview-check); process-video unchanged.
- [ ] root `README.md`: add the missing **ralph** row to the Available Plugins table; update the
      dev-workflow row to drop `/preview-check`.
- [ ] Static check: every `plugin.json` + `marketplace.json` parses as JSON; versions in each
      `plugin.json` match its `marketplace.json` entry.

### Task 6: Record E2E timings in the S3.5 prod gate (shard rebalancing)
Many new specs are added during a run, so the suite's shard balance goes stale. The post-review
full prod gate (S3.5) already runs the whole suite once — the natural place to refresh timings.
- [ ] In `execute.md` S3.5: when the project supports per-spec duration recording (a
      `--record-durations` flag, a documented durations mode, or an existing
      `tests/e2e/.spec-durations.json` the suite reads for sharding), run the mandatory
      full-suite gate **with timing capture enabled** — no extra run, since S3.5 already runs
      the whole suite once. This refreshes the durations file so the next run's shard balancing
      reflects the specs added this run.
- [ ] Capability-gate it ("if available"): detect durations support from the project's
      `test:e2e` script / playwright config (a record-durations flag or an existing
      `.spec-durations.json`). Unsupported → run the gate normally (no behavior change). If the
      gate already ran *without* recording, do ONE recorded rerun of the full suite.
- [ ] Commit the refreshed durations file in S4 finalize (a tracked source artifact, like the
      plan move) so future runs pick up the rebalanced timings; no-op when `e2e: unsupported`.
- [ ] Keep generic — read the project's durations convention (the T3 template uses
      `tests/e2e/.spec-durations.json`); don't hardcode a path.
- [ ] Static check: re-read S3.5 + S4 for coherence (record once, commit durations, no-op when
      e2e unsupported); grep `spec-durations|record-durations|S3.5` line up.

### Task 7: Verify
- [ ] `grep -rn "preview-check\|docs/previews"` across the repo → zero hits.
- [ ] Version consistency: ralph 0.4.1 and dev-workflow 0.1.1 agree between plugin.json and marketplace.json.
- [ ] JSON parse all manifests; `py_compile` build-demo.py.
- [ ] Re-read execute.md preflight + S3.5 timings + demo.md viewport flow once more for coherence.
- [ ] Confirm requirements met; note that going live requires push + `/plugin update` in a fresh session.
