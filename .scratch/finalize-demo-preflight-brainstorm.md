---
kind: brainstorm
slug: finalize-demo-preflight
artifact: docs/plans/.scratch/brainstorm-finalize-demo-preflight.md
status: plan-written
artifact_plan: docs/plans/2026-06-19-finalize-demo-and-preflight.md
created: 2026-06-19
updated: 2026-06-19
---

# Session manifest — finalize demo skill + port hardened preflight + version cleanup

Topic: finalise the `/ralph demo` skill (retire screenshots in PR prep in favour of the
demo video), port the locally-hardened execute preflight (dependency + repo-health probe)
from the installed cache 0.3.0 into the repo, then do a consistent version bump + cleanup.

## Context gathered (pre-interview)
- Thread A: `pr.md` Step 3 emits both Screenshots (from `/preview-check`, dev-workflow) and Demo lines.
- Thread B: hardened step-2 dependency probe exists ONLY in installed cache 0.3.0 (mtime 2026-06-18 19:55),
  NEVER committed to repo (`git log -S` empty). Repo has the naive `bun run lint`-based step 2.
- Thread C: plugin.json 0.4.0 vs marketplace.json ralph 0.3.0 (stale desc/keywords); root README omits ralph.
- Demo polish (from prior review): build-demo.py crashes in documented silent mode (no narration.json guard);
  marketplace/version drift.

## Checkpoint log
- 2026-06-19 — context sweep done (execute.md cache-vs-repo diff, pr.md, preview-check.md, memory files); manifest created; entering interview.
- 2026-06-19 — interview complete (4 decisions locked); dump written to docs/plans/.scratch/brainstorm-finalize-demo-preflight.md. Ready for /ralph plan.
- 2026-06-19 — /ralph plan: refinements applied (attempt `bun run up` first; DELETE /preview-check not deprecate; NEW desktop/mobile viewport step in demo). Single-mode plan (6 tasks) written to docs/plans/2026-06-19-finalize-demo-and-preflight.md. Routing: single mode (streams overlap on shared files; repo has no JS test harness).
