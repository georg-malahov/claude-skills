# Progress file

The progress file accumulates context across every phase of a run so the orchestrator, the review fixer, and **you the operator** can see what happened — without diving into any subagent's isolated context.

## Location — throwaway

```
/tmp/ralph-progress-<plan-stem>.txt
```

The progress file is **live runtime telemetry**, not resume state. Its only job is answering "is the run healthy right now / is the agent circling?" while the run is in progress. Once the run ends its value is gone.

Durable resume state lives elsewhere — the plan file's `[ ]`/`[x]` checkboxes and the session manifest's checkpoint log. `/ralph execute resume` reads those, never a stale progress file. So the progress file does not need to survive a reboot and does not belong in the repo: `/tmp` keeps it out of `git status`, needs no `.gitignore`, and gives wave mode a flat namespace (`/tmp/ralph-progress-<plan-a>.txt`, `/tmp/ralph-progress-<plan-b>.txt`) with no per-worktree `.scratch/` juggling.

Wave mode: one `/tmp/ralph-progress-<plan-stem>.txt` per plan.

## Scripts — always use them, never `cat >>`

Two bundled scripts under `${CLAUDE_PLUGIN_ROOT}/scripts/`:

- `init-progress.sh <file> <plan-path> <branch>` — writes the header. On an existing file (resume) it appends a `--- Resumed ---` marker instead of clobbering.
- `append-progress.sh <file> [message]` — appends one timestamped line; with no message argument it appends multi-line content from stdin.

Never write the progress file with `cat >>`, `printf >>`, or Edit. Always go through `append-progress.sh` — it owns the timestamp format and keeps writes consistent.

## File format

```
# progress
Plan: docs/plans/2026-05-20-<name>.md
Branch: <branch>
Started: 2026-05-20 16:40:11
---
[2026-05-20 16:40:13] [orch] dispatched ralph-task (sonnet) — Task 1: Add dbSystem client
[2026-05-20 16:42:55] [task] created db.test.ts (+151)
[2026-05-20 16:43:30] [task] validation: lint FAIL (3 errors, lib/auth.ts)
[2026-05-20 16:44:01] [task] stash-check: lint errors PRE-EXISTING
[2026-05-20 16:46:20] [task] commit a1b2c3d
[2026-05-20 16:46:25] [orch] Task 1 — completed
...
---
Completed: 2026-05-20 17:12:40
```

## Who writes what

Both the orchestrator and the running task/fixer subagent write to the file. The subagent writing its own milestones is essential — the orchestrator cannot see inside a running subagent, and mid-task circling is exactly what we need visible.

**Orchestrator (`[orch]`)** — coarse milestones, written from the main session:
- on dispatch: `[orch] dispatched ralph-task (sonnet) — Task N: <title>`
- on verdict: `[orch] Task N — completed` / `[orch] Task N — FAILED (retry 1)`
- before each review iteration: `--- review iteration N: <comprehensive|critical> ---`
- after review agents return: `[review] iteration N findings:` followed by the full agent output piped via `append-progress.sh` stdin mode
- after the fixer returns: `[fixer-summary] iteration N: <fixer FIXES report>`
- at completion: a `---` line then `Completed: <timestamp>`

**Task subagent (`[task]`)** — fine-grained milestones during its run (ralph's addition):
- task start, each file created/heavily modified, each validation run + result, each non-obvious decision (approach change, pre-existing-bug verdict), each commit, terminal `DONE`/`TASK_FAILED`.

**Fixer subagent (`[fixer]`)** — fine-grained during its run:
- findings received (count + severity), each fix applied (category + short SHA), validation result, terminal status.
- The fixer also **reads** the progress file on start — prior `[review]`/`[fixer-summary]` entries tell it what earlier iterations already found and fixed, so it does not re-report resolved issues.

**Review agents** — do NOT touch the progress file. They look at repository state and return findings; the orchestrator logs those findings under `[review]`.

## Line tags summary

| Tag | Writer | Granularity |
|---|---|---|
| `[orch]` | orchestrator | coarse — dispatch / verdict / phase |
| `[task]` | ralph-task | fine — per-milestone during the task |
| `[fixer]` | ralph-fixer | fine — per-fix during the round |
| `[review]` | orchestrator | the full review-agent output, per iteration |
| `[fixer-summary]` | orchestrator | the fixer's FIXES report, per iteration |

## Circling detection

The log is designed to make circling visible. When the orchestrator wakes (on a completion notification or a "check progress" request) it reads the tail and explicitly flags:

- the same `validation: X FAIL` line 3+ times for one task → the fix is not converging
- `decision: revert` more than once in a task → thrashing between approaches
- a long gap between the last timestamp and now with no terminal line → stuck or in a slow op

Flag these proactively — do not just relay raw lines.

## Reading it — for the operator

Any time, independent of the orchestrator:

```bash
tail -30 /tmp/ralph-progress-<plan-stem>.txt
```

That answers "what is the agent doing right now, and is it fine?" without entering any subagent's context.
