---
description: Ralph execute — native ralph-loop. Auto-detects single-plan vs wave mode.
argument-hint: '[resume]'
---

# /ralph execute

Runs the ralph-loop natively. **No Docker, no external CLI.** All execution is via the Agent tool from this session.

## Execution model — event-driven, non-blocking

`/ralph execute` does **not** block the session for the whole run. It is an **event-driven orchestrator**: each time it is invoked it reconciles state, does ONE step, and ends its turn. The session returns to you between steps — you can ask for status or intervene at any time.

It gets invoked three ways:
1. You type `/ralph execute` (fresh start or resume).
2. A background subagent completes — the harness **automatically re-invokes** the orchestrator (no polling, no sleep).
3. You send a message while agents run (e.g. "check progress", "pause").

**On every invocation, the orchestrator runs the RECONCILE procedure** (below), does one step, ends the turn. Durable state lives in two files, not in the conversation: the plan file (`[ ]`/`[x]` boxes) and the session manifest (checkpoint log). The progress file (`/tmp/ralph-progress-<plan-stem>.txt`) is live telemetry — useful while the run is in flight, not relied on for resume. Any invocation can rebuild full context from the plan + manifest.

## Step 0 — Mode detection

Look for an execution manifest at `docs/plans/*-execution.md`:
- **Manifest present** → wave mode (Step W*)
- **No manifest, single plan in `docs/plans/`** (unfinished — has `[ ]` boxes) → single mode (Step S*)
- **No manifest, no unfinished plan** → standalone fallback. Scan `docs/plans/` and `docs/plans/completed/`:
  - **If any plan has `[ ]` boxes** (incomplete) → offer to resume those plans (list them via AskUserQuestion). This includes plans that finished tasks but never went through the review loop.
  - **No incomplete plans, but completed ones exist** → ask:
    - "Re-review a completed plan" — runs S2 (review loop) only against the diff that plan introduced (`git log --grep '<plan-stem>'` for the range)
    - "Run `/ralph plan` first" (Recommended)
    - "Cancel"
  - **Nothing at all** → tell the user there is nothing to execute; suggest `/ralph plan` or `/ralph brainstorm`.
- **`resume` argument** → read manifest's `Current State` (wave) or plan checkboxes (single) and pick up.

Never "re-run" a completed plan. Valid follow-ups are *resume the incomplete one* or *review the completed one again*.

If multiple manifests exist with non-`completed` state, ask the user which to execute.

## Session manifest

Create per dispatcher spec (`commands/ralph.md` → "Session manifests"). `kind: execute`. `artifact:` points at the plan file (single) or execution manifest (wave). Add two custom frontmatter lines: `progress: /tmp/ralph-progress-<plan-stem>.txt` so a resuming session can find the live progress file if it still exists, and `dispatches: 0` — the durable count of `ralph-task` dispatches that the RECONCILE 50-cap reads (incremented on every dispatch, so the cap holds across a resume).

Durable resume state is the plan checkboxes + (wave) the manifest's `Current State`. Checkpoint the session manifest after each task verdict, wave transition, and review iteration.

## Step 1 — Pre-flight (both modes, runs once at start)

- `git status` clean (warn if not)
- `git branch --show-current` — not main/master
- If any plan has a `### BEFORE LAUNCH (host)` section: verify `package.json` + `bun.lock` already include the listed packages (`bun pm ls | grep <pkg>`). If missing, STOP and ask the user to install on the host.

No image build check — there is no image.

**Initialize the progress file** with the bundled script (`prompts/progress.md` has the full spec):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/init-progress.sh" \
  /tmp/ralph-progress-<plan-stem>.txt \
  docs/plans/<plan-file>.md \
  "$(git branch --show-current)"
```

On an existing file (resume), the script appends a `--- Resumed ---` marker instead of clobbering. All later writes — orchestrator and subagents — go through `${CLAUDE_PLUGIN_ROOT}/scripts/append-progress.sh`. Never `cat >>` the progress file directly. The progress file is throwaway telemetry in `/tmp`; it is not committed and not the resume state.

---

## SINGLE MODE (S)

### RECONCILE — run at the top of every invocation

Process events in this order — a user message and a subagent completion can land in the same invocation, so the user message is handled **first** and does not consume a pending completion:

1. **Re-read the plan file** (subagents modify it).
2. **If the user sent a message** → handle it first:
   - `pause` / `stop` → **S-Pause**. Stop here.
   - `check progress` / `status` → **S-Status**, then fall through to step 3 (a completion may also be pending this invocation).
   - anything else → answer it. If a subagent also completed this invocation (step 3 applies), fall through; otherwise end the turn (agents keep running).
3. **Check for a just-completed background subagent** whose result you have not yet processed (its task id is recorded in the session manifest as `running`):
   - If found → go to **S2 — Task verdict**.
4. **If no subagent is running and `[ ]` tasks remain** → go to **S1 — Dispatch**.
5. **If no subagent is running and no `[ ]` tasks remain** → go to **S3 — Review loop**.

Outer safety cap: **50 dispatches** total. The count is durable — the orchestrator increments `Dispatches:` in the session manifest on every `ralph-task` dispatch (S1) and reads it back here, so the cap survives a resume. If `Dispatches:` ≥ 50, stop and surface — the plan is too large or something is stuck.

### S1 — Dispatch next task

1. Find the first task with `[ ]` checkboxes.
2. Announce it to the user (task number + title + its `[ ]` items).
3. Dispatch `ralph-task` **in the background**:
   - `subagent_type: "ralph-task"`, `run_in_background: true`
   - Prompt includes: the full plan file, the single task as the target, the project CLAUDE.md, the contract text from `prompts/task.md`, **the progress file path**, and **the absolute path of `${CLAUDE_PLUGIN_ROOT}/scripts/append-progress.sh`** (resolve `${CLAUDE_PLUGIN_ROOT}` to its real path before passing — the subagent does not inherit the variable).
4. Log: `append-progress.sh <progress-file> "[orch] dispatched ralph-task (sonnet) — Task N: <title>"`.
5. Record the task id as `running` in the session manifest and **increment its `Dispatches:` counter** (the durable dispatch count the RECONCILE cap reads).
6. **End the turn** with a status line:
   > Task N/M dispatched in background. Session is free — ask "check progress" anytime. I'll continue automatically when it completes.

Do NOT wait. Do NOT poll. The harness re-invokes you on completion.

### S2 — Task verdict (on background completion)

1. Read the subagent's return summary and the **tail of the progress file**.
2. Re-read the plan. Are task N's `[ ]` boxes now `[x]` and is there a commit?
3. **Green** → `append-progress.sh <progress-file> "[orch] Task N — completed"`. Mark the task id `completed` in the manifest. Go to RECONCILE (which dispatches the next task).
4. **Not green / `TASK_FAILED`**:
   - **First failure** → `append-progress.sh <progress-file> "[orch] Task N — FAILED (retry 1)"`. Re-dispatch the same task in the background (S1 with a retry note in the prompt). End turn.
   - **Retry also failed** → `append-progress.sh <progress-file> "[orch] Task N — FAILED after retry"`. **Do NOT auto-advance.** Surface via AskUserQuestion (turn stays open for your decision):
     - "Edit plan and retry" — you revise the plan; restart that task with a fresh 2-attempt budget
     - "Skip task and continue" — mark `[~]` + `<!-- SKIPPED: <reason> -->`, continue
     - "Abort" — stop the run

**Per-task budget:** 2 background dispatches (1 + 1 retry). No more without user intervention.

### S-Status — on "check progress"

1. Read the tail (~30 lines) of `/tmp/ralph-progress-<plan-stem>.txt`.
2. Summarize: current task, recent milestones, last timestamp.
3. **Flag circling explicitly** (per `prompts/progress.md`): same `validation: X FAIL` 3+ times, repeated `decision: revert`, or a long stale gap with no `DONE`.
4. If circling is detected, proactively offer: "this task looks stuck — want to pause and edit the plan?"
5. End the turn. The background agent keeps running.

### S-Pause — on "pause" / "stop"

1. Stop the running background subagent with `TaskStop` (its id is in the manifest; if `TaskStop` is not loaded, `ToolSearch` for it first).
2. `append-progress.sh <progress-file> "[orch] paused by user at Task N"`.
3. Set the session manifest `status` checkpoint to paused-at-task-N.
4. Confirm: "Paused at Task N. Resume with `/ralph execute resume`."

### S3 — Review loop (all tasks done)

Read `prompts/review.md` (override chain) and execute it as a playbook from THIS session. The unified loop:
- Iteration 1: comprehensive 5-agent fan-out (dispatch the 5 reviewer subagents — they are short-lived, dispatch foreground in one parallel message and wait; reviewers are read-only and fast)
- Iterations 2–5: critical-only (`ralph-quality` + `ralph-implementation`)
- After each iteration: one `ralph-fixer` subagent with the full findings list
- Exit: all clean | HEAD unchanged after fixer | iteration cap (5)

Progress logging during review (per `prompts/progress.md`):
- Orchestrator, before each iteration: `append-progress.sh <progress-file> "--- review iteration N: <comprehensive|critical> ---"`.
- Orchestrator, after review agents return: pipe the **full** agent output into the progress file via stdin mode — `echo "<findings>" | append-progress.sh <progress-file>` — under a `[review] iteration N findings:` line.
- The `ralph-fixer` subagent appends its own `[fixer]` lines and the orchestrator logs the fixer's FIXES report as `[fixer-summary]`.
- Review agents themselves do NOT write the progress file — they return findings, the orchestrator logs them.

Fan-out must be initiated from this session — subagents cannot spawn subagents.

### S4 — Finalize

- Final lean validation (`lint && typecheck && test:unit`)
- Ensure all `[ ]` boxes are `[x]`
- Move the plan to `docs/plans/completed/`; commit the move
- `append-progress.sh <progress-file> "plan complete"` then append a `---` line and `Completed: <timestamp>`

### S5 — Handoff

If `RALPH_AUTO_PR` is set:
- user said `"hardened"` / `"with review"` → chain into `/ralph review`
- otherwise → chain into `/ralph pr` (lean)

Otherwise ask via AskUserQuestion:
- "Visual review (`/ralph review`)" (Recommended)
- "Create PR now (`/ralph pr`)" — lean, no review, no E2E
- "Stop"

---

## WAVE MODE (W)

Wave mode is single mode, multiplied. Same per-task `ralph-task` dispatch, same fresh context per task — the only difference is that the orchestrator runs **one task loop per active plan, concurrently**, and each plan lives in its own git worktree.

**The orchestrator (this session) is the single dispatcher.** It spawns every `ralph-task` directly — they are all leaf subagents, no nesting. Parallelism comes from having N `ralph-task` agents in flight at once (one per plan), not from any agent spawning another.

**Within a plan: sequential.** Tasks of one plan are usually dependent (task 2 builds on task 1), so the orchestrator keeps at most one `ralph-task` per plan in flight. **Across plans: parallel** — plan A's task 3, plan B's task 1, plan C's task 2 all run at the same time.

### Worktree isolation — how parallel plans avoid clobbering each other

Two `ralph-task` agents committing in the same working tree at the same time corrupts the git index. So each plan gets its own **git worktree** — a separate working directory with its own index and branch, exactly as ralphex isolated each plan. Single mode needs no worktree (one agent at a time, no contention); wave mode requires one per plan.

Worktrees live under `.ralph/worktrees/` **inside the target repo**. Git does not auto-ignore a worktree directory nested in its own repo — it shows as untracked and would trip the Step 1 `git status` clean check (and risk being committed). So before creating any worktree the orchestrator ensures the target repo ignores it:

```bash
grep -qxF '.ralph/' .gitignore 2>/dev/null || { echo '.ralph/' >> .gitignore && git add .gitignore && git commit -m "chore: ignore .ralph worktree dir"; }
```

Then it creates one worktree per plan on the host:

```bash
git worktree add .ralph/worktrees/<plan-stem> -b ralph-<plan-stem>
```

The plan files are committed on the base branch by `/ralph plan` (commit them before launching the wave if not), so each worktree — branched from HEAD — already contains them; no copy is needed. Only `cp docs/plans/<plan-file>.md .ralph/worktrees/<plan-stem>/docs/plans/` if a plan file is still uncommitted.

A `ralph-task` subagent runs in the **main session's** cwd, not the worktree (subagents inherit the parent cwd; `cd` does not persist across their Bash calls). So each wave-mode dispatch tells the agent its **worktree root** as an absolute path, and the agent contract requires:
- every Bash command prefixed with `cd <worktree-abs-path> && …`
- `git -C <worktree-abs-path> …` for any git command
- absolute paths under the worktree root for Read / Write / Edit

The progress file (`/tmp/...`) and the `append-progress.sh` path are absolute and cwd-independent — they work unchanged from any worktree.

### W1 — Launch current wave

Ensure `.ralph/` is gitignored once (command above). Then for each plan in the current wave (from the manifest):

1. Create the worktree (command above). The worktree already has the plan file via the base-branch commit — only `cp` it in if uncommitted.
2. Init the plan's progress file: `/tmp/ralph-progress-<plan-stem>.txt` (flat `/tmp` namespace — one place to read them all).
3. Dispatch the plan's **first** `[ ]` task as a background `ralph-task` (`run_in_background: true`), with the dispatch prompt carrying the **worktree root absolute path** plus everything from S1 step 3.
4. Record each plan's in-flight task id in the manifest's Execution Log.

All N first-tasks launch together — that is the parallelism.

### W-RECONCILE — multi-plan, runs at the top of every invocation

Same as single-mode RECONCILE, extended across plans — user message handled first so it is never dropped by a concurrent completion:

1. Re-read every active plan file.
2. **If the user sent a message** → handle it first: `pause` → stop all in-flight agents (S-Pause across plans), done; `check progress` → W-Status, then fall through; anything else → answer it, fall through if a completion is also pending else end turn.
3. **A background subagent completed** → identify which plan it belonged to (its task id is recorded per-plan in the manifest) → run W2 verdict for *that plan only*; the other plans keep running untouched.
4. For any plan with no in-flight agent and `[ ]` tasks remaining → dispatch its next task (W1 step 3, incrementing `Dispatches:` — the 50-cap counts dispatches across all plans).
5. When every plan in the wave has all tasks `[x]` → W3.

### W2 — Per-plan task verdict

Identical to S2, scoped to the completed plan: green → log + advance that plan's next task; failed → one retry; retry failed → surface to user (that plan pauses, others continue).

### W-Status — on "check progress"

Read every plan's `/tmp/ralph-progress-<plan-stem>.txt` and summarize per plan: current task, recent milestones, circling flags. One compact block per plan.

### W3 — Wave transition

When all plans in the wave have every task `[x]`:
- Any plan ended failed/skipped → ask the user (fix and retry / accept / abort).
- All green → merge the wave's branches into the parent branch **one at a time** (sequential two-way merges, NOT an octopus merge — a single `git merge A B C` octopus aborts wholesale on any conflict and leaves no conflicted index to resolve):
  ```bash
  for b in ralph-<plan-stem-1> ralph-<plan-stem-2> …; do git merge --no-ff "$b" || break; done
  ```
  Parallel plans should be file-disjoint by design. If a merge does conflict, the loop stops on that branch — resolve the conflict and commit before merging the rest.
- Advance to the next wave (back to W1).

### W4 — Merge wave

The final merge plan runs as a full **single-mode** loop (S1–S4) in its own worktree — tasks **and** the review loop. The git-diff-driven review covers the consolidated change surface; per-branch pre-merge review would produce false positives about missing wiring.

Per-wave plans run tasks-only; the merge plan runs the full pipeline.

### W5 — Cleanup + handoff

- Set manifest `Current State: completed`
- `git worktree prune`; remove `.ralph/worktrees/*`
- Move the manifest to `docs/plans/completed/`
- Handoff per S5

## Resume

`/ralph execute resume` — read the manifest + plan checkboxes (the durable resume state), recreate any removed worktrees from their branches, re-init the progress file (the script appends a `--- Resumed ---` marker), and re-enter RECONCILE. Because resume state lives in the plan + manifest, resume works even if the old `/tmp` progress file is gone.
