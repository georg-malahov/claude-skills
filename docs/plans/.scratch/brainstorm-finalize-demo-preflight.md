# Brainstorm: finalise /ralph demo + port hardened preflight + version cleanup
Date: 2026-06-19

## Summary
Three independent but co-shipped changes to the `ralph` plugin (and one small change to
`dev-workflow`), bundled into a single consistent version bump:

1. **Demo replaces screenshots in PR prep.** `/ralph demo` (shipped 0.4.0) produces a
   narrated walkthrough video that is a strictly better PR visual than static route
   screenshots. So PR prep stops referencing screenshots, and the screenshot tool
   (`/preview-check` in dev-workflow) is **deprecated**.
2. **Port the hardened preflight.** The dependency/repo-health probe in `execute.md` step 2
   was hardened in the *installed cache* (0.3.0, edited 2026-06-18) while working in other
   projects, but **never committed back** — the repo still has the naive `bun run lint`-based
   version. Port the hardened version verbatim, and **extend it with an E2E-runtime
   readiness check** (Docker daemon + sidecars) so the preflight actually guarantees E2E can
   run, per the stated goal.
3. **Consistent version bump + cleanup.** Bump to **0.4.1**, sync the stale
   `marketplace.json` (install source-of-truth) and add `ralph` to the root README, and fold
   in two demo polish fixes found in the prior review.

## Goals
- PR prep links a narrated demo as the canonical visual; no screenshot machinery in the path.
- The execute preflight reliably answers "are deps installed and is the repo healthy enough
  to run lean validation AND E2E?" before dispatching any task — by **probing, not assuming**
  (lint / `--version` / `.bin` all pass on a broken dep graph, so they are not signals).
- Generic across the standard T3 + ZenStack + Better Auth template repos, not hardcoded to
  one project — detect runner name / run_prefix / Docker shape, don't bake in paths.
- One coherent version across plugin.json + marketplace.json + README; no drift.

## Decisions locked (interview, 2026-06-19)
| # | Question | Decision |
|---|----------|----------|
| 1 | Screenshots vs demo in PR prep | **Remove screenshots AND deprecate `/preview-check`** |
| 2 | Preflight port scope | **Port hardened deps probe verbatim + extend to E2E-runtime readiness** |
| 3 | Version + consistency | **0.4.1 + sync marketplace.json & root README** |
| 4 | Demo polish fixes | **Fold in both** (silent-mode build-demo guard + demo.md HTML-description note) |

## Scope of changes (the concrete work, for /ralph plan)
**ralph plugin**
- `commands/execute.md` — replace step-2 ("Dependencies ready?") with the hardened cache-0.3.0
  text (deps-resolve sanity check + lockfile staleness + typecheck/test:unit authoritative
  probe + 3 remediation paths + calibrated HARD-STOP). Then ADD an E2E-runtime readiness
  sub-check to step 3/3b: when `e2e != unsupported`, verify Docker daemon responsive
  (`docker info`) and declared sidecars (DB / GreenMail-mail / compose services) reachable or
  startable at preflight; if not, degrade `e2e` to not-runnable instead of failing late in
  S3.5. Reuse the existing "host-orchestrating entrypoint" classification (3b) — don't
  double-launch sidecars the entrypoint already owns.
- `commands/pr.md` — delete the **Screenshots:** line (Step 3); demo is the visual companion.
- `scripts/demo/build-demo.py` — guard missing/empty `narration.json`: when absent, skip the
  audio mux (no `amix=inputs=0`) and transcode `webm→mp4` directly; VTT + chapters + page
  still build. Makes the documented silent-mode degradation actually work.
- `commands/demo.md` — Step 5: note that the `demo-meta.json` description is injected as
  inline HTML.
- `.claude-plugin/plugin.json` — 0.4.0 → 0.4.1.
- `README.md` (plugin) — reflect screenshot retirement + preflight hardening if mentioned.

**dev-workflow plugin**
- `commands/preview-check.md` — mark **deprecated** (point users at `/ralph demo`). Verify
  `commands/orchestrate.md` / `commands/create-pr.md` don't reference it or `docs/previews/`
  (preview-check says it was never wired in — confirm). Bump dev-workflow if it changes.

**marketplace + root**
- `.claude-plugin/marketplace.json` — ralph `version` 0.3.0 → 0.4.1, refresh description
  (add demo) + keywords (`demo`); bump dev-workflow entry if deprecation lands there.
- root `README.md` — add the missing `ralph` row to the Available Plugins table.

## Non-goals
- The two known TODOs from `project_ralph_perf_next_steps`: the `ralph-perf` command and
  wave per-task-container E2E. Out of scope here.
- Re-architecting the demo pipeline; only the silent-mode guard + the doc note.
- Building new screenshot capability; we are removing that path, not improving it.

## Constraints
- **Generic, not theomedis-specific** — detect architecture (runner, run_prefix, Docker shape,
  sidecar set) from the project; the standard template gives us known shapes but no hardcoded
  paths. (Design principle from `project_ralph_perf_next_steps`: capability detection over
  user-facing mode menus; verify by probing before acting.)
- **Host-side deps only** — preflight auto-install runs on the host, never an agent adding a
  dep mid-run (matches `feedback_ralphex_host_deps` + global CLAUDE.md).
- **marketplace.json is the install source-of-truth** — must not stay behind plugin.json.
- Artifacts (video/screenshots) hosted, never committed — unchanged.

## Open questions (for the plan phase)
- E2E-runtime readiness: how aggressive at preflight? Just *probe + degrade* (don't start
  sidecars), or *start sidecars if the project defines a start command*? Leaning: probe +
  attempt the project's documented start (e.g. `bun run up`), degrade if still unreachable —
  mirroring the deps "auto-install once then re-verify" policy.
- Does deprecating `/preview-check` mean delete-after-a-grace-period or just a banner? Leaning:
  banner + redirect now, delete in a later cleanup.
- dev-workflow version bump: needed only if we touch its files (deprecation banner) — confirm
  whether to bump 0.1.0 → 0.1.1 and sync its marketplace entry.

## Repo context (from the sweep)
- Hardened step-2 confirmed ONLY in installed cache `~/.claude/plugins/cache/.../ralph/0.3.0/
  commands/execute.md` (mtime 2026-06-18 19:55); `git log -S` shows it never entered repo
  history. Repo 0.3.0 commit (63b09d0, 2026-06-17) shipped the naive step 2.
- cache-0.3.0-vs-repo diff: ONLY `execute.md` step 2 drifted as local hardening; all other
  diffs (ralph.md, pr.md, README) are the repo being AHEAD with 0.4.0 demo work.
- `pr.md` Step 3 currently emits both Screenshots (from `/preview-check` → `docs/previews/`)
  and Demo lines. `/preview-check` lives in dev-workflow, is manual, and is NOT yet wired into
  orchestrate/create-pr (per its own note).
- `build-demo.py` line 37 unconditionally opens `narration.json`; `amix=inputs=0` invalid →
  documented silent mode crashes today.
- Version drift: plugin.json 0.4.0 vs marketplace.json ralph 0.3.0; root README omits ralph.
- Memory: `project_ralph_perf_next_steps` (status, TODOs, design principle), `feedback_ralphex_
  host_deps` (host-side deps rule), `project_ralph_consolidation` (two-ralph-systems caution).

## Raw interview log
- Mode: decide. Scope: finalise demo + port hardened preflight + version cleanup.
- Q1 Visuals in PR → **Remove screenshots AND deprecate /preview-check**
- Q2 Preflight scope → **Port verbatim + extend to E2E-runtime readiness**
- Q3 Version + consistency → **0.4.1 + sync marketplace & README**
- Q4 Demo polish → **Fold in both fixes**
