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

Create per dispatcher spec (`commands/ralph.md` → "Session manifests"). `kind: execute`. `artifact:` points at the plan file (single) or execution manifest (wave). Add a custom frontmatter line `progress: /tmp/ralph-progress-<plan-stem>.txt` so a resuming session can find the live progress file if it still exists.

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

1. **Re-read the plan file** (subagents modify it).
2. **Check for a just-completed background subagent** whose result you have not yet processed (its task id is recorded in the session manifest as `running`):
   - If found → go to **S2 — Task verdict**.
3. **If the user sent a message** → handle it: `pause` → S-Pause; `check progress` / `status` → S-Status; anything else → answer it, then end turn (agents keep running).
4. **If no subagent is running and `[ ]` tasks remain** → go to **S1 — Dispatch**.
5. **If no subagent is running and no `[ ]` tasks remain** → go to **S3 — Review loop**.

Outer safety cap: **50 dispatches** total. If exceeded, stop and surface — the plan is too large or something is stuck.

### S1 — Dispatch next task

1. Find the first task with `[ ]` checkboxes.
2. Announce it to the user (task number + title + its `[ ]` items).
3. Dispatch `ralph-task` **in the background**:
   - `subagent_type: "ralph-task"`, `run_in_background: true`
   - Prompt includes: the full plan file, the single task as the target, the project CLAUDE.md, the contract text from `prompts/task.md`, **the progress file path**, and **the absolute path of `${CLAUDE_PLUGIN_ROOT}/scripts/append-progress.sh`** (resolve `${CLAUDE_PLUGIN_ROOT}` to its real path before passing — the subagent does not inherit the variable).
4. Log: `append-progress.sh <progress-file> "[orch] dispatched ralph-task (sonnet) — Task N: <title>"`.
5. Record the task id as `running` in the session manifest.
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

1. Stop the running background subagent (`TaskStop` with its id).
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

> **⚠ Wave mode needs a design rework before use.** The original design had each per-plan background worker spawn `ralph-task` subagents — but **subagents cannot spawn subagents** (Claude Code constraint). The text below is the corrected interim design; treat wave mode as experimental until it has been tested end-to-end. Single mode is the validated path.

### W1 — Launch current wave

For each plan in the current wave (from the manifest):

1. Create a host-side worktree:
   ```bash
   git worktree add .ralph/worktrees/<plan-stem> -b ralph-<plan-stem>
   ```
2. Copy the plan file into the worktree:
   ```bash
   cp docs/plans/<plan-file>.md .ralph/worktrees/<plan-stem>/docs/plans/
   ```
3. Initialize a progress file for this plan: `/tmp/ralph-progress-<plan-stem>.txt` (flat `/tmp` namespace — no per-worktree path juggling).

**Dispatch model (corrected):** the orchestrator (this session) is the *single* dispatcher. It does NOT spawn one "plan worker" per plan that then spawns `ralph-task` — that nesting is impossible. Instead the orchestrator drives all plans' task loops itself, interleaved:

- For each active plan, dispatch its next `[ ]` task as a background `ralph-task`, with the prompt instructing the agent that **all paths are rooted at the worktree absolute path** (subagents start in the main cwd and `cd` does not persist, so the agent must use absolute paths or `cd` at the start of each Bash call).
- Multiple `ralph-task` dispatches are in flight at once — one per plan — giving real parallelism without nesting.
- The orchestrator's RECONCILE handles completions from any plan and dispatches that plan's next task.

Record task ids per plan in the manifest's Execution Log.

### W2 — Status

On "check progress" / "status": read every plan's progress file (`/tmp/ralph-progress-<plan-stem>.txt`, one per plan) and summarize per plan. Flag circling per plan.

### W3 — Wave transition

When all plans in the wave have all tasks `[x]`:
- Any plan failed → ask user (fix and retry / skip / abort)
- All green → merge wave branches into the parent branch:
  ```bash
  git merge ralph-<plan-stem-1> ralph-<plan-stem-2> ...
  ```
- Advance to the next wave (W1)

### W4 — Merge wave

The merge plan runs as a full **single-mode** loop (S1–S4) in its own worktree — tasks **and** the review loop. The git-diff-driven review covers the consolidated change surface; per-branch pre-merge review would produce false positives about missing wiring.

Per-wave plans run tasks-only; the merge plan runs the full pipeline.

### W5 — Cleanup + handoff

- Set manifest `Current State: completed`
- `git worktree prune`; remove `.ralph/worktrees/*`
- Move the manifest to `docs/plans/completed/`
- Handoff per S5

## Resume

`/ralph execute resume` — read the manifest + plan checkboxes (the durable resume state), recreate any removed worktrees from their branches, re-init the progress file (the script appends a `--- Resumed ---` marker), and re-enter RECONCILE. Because resume state lives in the plan + manifest, resume works even if the old `/tmp` progress file is gone.
