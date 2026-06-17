---
description: Ralph execute — native ralph-loop. Auto-detects single-plan vs wave mode.
argument-hint: '[resume]'
---

# /ralph execute

Runs the ralph-loop natively. **ralph itself orchestrates no containers or images** (unlike ralphex) — all orchestration is via the Agent tool from this session. It still runs the *project's* commands however the project requires: the Step 1 probe resolves a `run_prefix` (empty on host-native projects, `bun run dx` or similar for Docker-in-container projects) and every command + task dispatch goes through it.

## Execution model — event-driven, non-blocking

`/ralph execute` does **not** block the session for the whole run. It is an **event-driven orchestrator**: each time it is invoked it reconciles state, does ONE step, and ends its turn. The session returns to you between steps — you can ask for status or intervene at any time.

It gets invoked three ways:
1. You type `/ralph execute` (fresh start or resume).
2. A background subagent completes — the harness **automatically re-invokes** the orchestrator (no polling, no sleep).
3. You send a message while agents run (e.g. "check progress", "pause").

**On every invocation, the orchestrator runs the RECONCILE procedure** (below), does one step, ends the turn. Durable state lives in two files, not in the conversation: the plan file (`[ ]`/`[x]` boxes) and the session manifest (checkpoint log). The progress file (`${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt`) is live telemetry — useful while the run is in flight, not relied on for resume. Any invocation can rebuild full context from the plan + manifest.

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

Create per dispatcher spec (`commands/ralph.md` → "Session manifests"). `kind: execute`. `artifact:` points at the plan file (single) or execution manifest (wave). Add three custom frontmatter lines: `progress: ${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt` so a resuming session can find the live progress file if it still exists, `dispatches: 0` — the durable count of `ralph-task` dispatches that the RECONCILE 50-cap reads (incremented on every dispatch, so the cap holds across a resume) — and the **capability profile** resolved by the Step 1 probe, recorded as a small `env:` block (`exec_mode`, `run_prefix`, `e2e`, `e2e_cmd`, `worktree_isolation`). S1/S2/S3.5 and resume read it back; resume does not re-probe unless the block is missing.

Durable resume state is the plan checkboxes + (wave) the manifest's `Current State`. Checkpoint the session manifest after each task verdict, wave transition, and review iteration.

## Step 1 — Pre-flight (both modes, runs once at start)

- `git status` clean (warn if not)
- `git branch --show-current` — not main/master
- If any plan has a `### BEFORE LAUNCH (host)` section: verify `package.json` + `bun.lock` already include the listed packages (`bun pm ls | grep <pkg>`). If missing, STOP and ask the user to install on the host.

No image build check — there is no image.

### Environment & capability probe — the hardened preflight (run once, record in `env:`)

Before dispatching any task, determine **how this project runs** and **what can actually run**. Infer, then **verify by running cheap probes** — a fresh git worktree has no `node_modules` (it is gitignored), so assuming "lint works" without checking makes every task fail identically. There is **no E2E mode menu**: E2E is mandatory when the probe finds it runnable, and the loop degrades to lean-only when it isn't.

**1. Execution mode + run prefix.** How are project commands invoked?
- **Docker-in-container** — the project ships a container wrapper (a `dx` script in `package.json`, a `compose.*.yml` / `Dockerfile`, an `image:build` script, or `.claude/docker/`). Commands run through it: `run_prefix = "bun run dx"` (or the project's equivalent). Deps live in the container's `node_modules` volume.
- **Host-native** — no wrapper. `run_prefix = ""`; deps live in the worktree's own `node_modules`.

ralph the orchestrator manages **no** containers or images itself (unlike ralphex) — it only delegates project commands through `run_prefix`, which may itself enter a container. Record `exec_mode` + `run_prefix` in `env:`.

**2. Dependencies ready? (auto-install, then verify.)** Probe that lean validation can actually run: `<run_prefix> bun run lint` (or a fast `--help` / no-op typecheck), and check `node_modules/.bin`.
- **Missing / unusable** → **auto-install once on the host, then re-verify** (the chosen policy): Docker project → ensure the container + volume are up (`bun run up`); host-native → `bun install` in the worktree. The orchestrator does this on the **host** at preflight — this is environment setup, not an agent adding a new dependency mid-run, so it is consistent with the "host-side deps only" rule.
- **Still cannot run lean validation after install → HARD-STOP.** Surface the exact command the user must run. Never dispatch tasks onto a broken environment.

**3. E2E capability → `e2e:`.**
- **`unsupported`** — no `test:e2e` script, no `playwright.config`, or no browsers. → lean-only for the whole run; tasks leave `FIXME(e2e)` placeholders (original behavior). State this explicitly at start.
- **`dev+prod`** — E2E exists AND a dev-server E2E path is runnable (a documented dev-E2E command, or `playwright.config` `webServer` with `reuseExistingServer`, plus browsers). → per-task dev E2E (single mode) **and** the final prod gate (S3.5).
- **`prod-only`** — E2E exists but no runnable dev path. → no per-task E2E; final prod gate only.

**3b. Prod E2E command → `e2e_cmd` (resolve whenever `e2e != unsupported`).** The S3.5 prod gate needs the *entrypoint*, which is **not** always `<run_prefix> bun run test:e2e`. Read the project's `test:e2e` script and classify it:
- **Thin runner** — `test:e2e` is essentially a bare `playwright test` (build + Playwright, no container or sidecar orchestration of its own). → `e2e_cmd = "<run_prefix> bun run test:e2e"`: prefix it like every other command.
- **Host-orchestrating entrypoint** — `test:e2e` *itself* decides how to reach the runtime (e.g. branches on an env flag such as `RALPHEX_DOCKER` to enter the container) **and/or** launches sidecars **host-side** (GreenMail/mail, a DB, `compose` services) before running the inner suite. → `e2e_cmd = "bun run test:e2e"` **with no `run_prefix`**. Prefixing it with `bun run dx` would run the orchestrator *inside* the container — skipping the host-side sidecar launch and the env-flag branch — so mail/DB-dependent specs fail. Let the entrypoint own container entry; ralph just invokes it host-side. (The same caution applies to the dev-E2E command below: don't prefix a script that already self-orchestrates.)

Detect the host-orchestrating case from the script body: it shells out to a wrapper (`.sh`/`.ts`), chains `&&`/`compose up`/sidecar startup, or reads a Docker env flag — rather than being a bare `playwright test`. Record `e2e_cmd` in the `env:` block; **S3.5 runs `<e2e_cmd>` verbatim and does not re-prefix it.**

**4. Worktree isolation (wave only) → `worktree_isolation:`.** `docker-per-worktree` if each worktree can run its own container, else `shared-host`. **Current phase:** per-task dev E2E is **single-mode only** regardless — wave runs lean per-task and gets E2E via the final prod gate on the merged app. This field is recorded for the planned wave-per-task-E2E follow-up but does not change behavior yet.

Write the resolved `env:` block to the manifest immediately. **E2E is mandatory when available — no opt-out.** (Autonomous runs included; if E2E is `unsupported` the loop is lean-only automatically.)

### Dev server during execution — capability-driven

**Default (`e2e: unsupported` or `prod-only`, and ALL wave mode): no dev server.** Lean validation (`lint → typecheck → test:unit`) needs no running app — `tsc` and Vitest read source directly, they do not hit `localhost:3000` or read `.next/`. A `next dev` (Turbopack) watcher is pure waste, and in wave mode actively harmful:

- **Recompile storm.** Every edit triggers Turbopack recompile + HMR. In wave mode, N worktrees × `next dev` = N watchers churning on every edit, for output nobody consumes.
- **Resource contention.** Recompiles compete for CPU/RAM with the agent's own `tsc` + Vitest — slower validation, flakier timing-sensitive unit tests.

So in these modes: **do not start a dev server, and do not let the environment start one for you.** If the devcontainer / `compose` / `bun run dx` wrapper auto-starts `next dev` as its entrypoint, run ralph against a variant whose entrypoint does *not*. The task contract (`prompts/task.md`) forbids agents from starting one. (`.next/` is gitignored by every Next.js scaffold, so a stray dev server never pollutes commits.)

**`e2e: dev+prod`, single mode: ONE warm dev server, kept alive for the whole run.** This is the deliberate exception. Here the recompiles are not waste — they are the hot-reload that lets each task run its freshly-authored spec immediately, and single mode runs one task at a time so there is exactly one server and no storm. Pre-flight (resolve once, reuse across tasks — generic, **not** hardcoded to any one project):

1. **Resolve the dev-E2E command.** Prefer a documented headless dev-E2E script; else `<run_prefix> playwright test <spec>` relying on `reuseExistingServer` in `playwright.config`. Read the config to pin `--project` / base-URL so a single spec runs **once**, not once per project.
2. **Ensure the warm dev server is up** — e.g. the one `bun run up` / the devcontainer already runs — and keep it alive across tasks; do not restart it per task.
3. **Pass `run_prefix`, the dev-E2E command, and the dev base URL** to every task dispatch (S1) so the task contract's dev-E2E variant activates.

**Initialize the progress file** with the bundled script (`prompts/progress.md` has the full spec):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/init-progress.sh" \
  "${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt" \
  docs/plans/<plan-file>.md \
  "$(git branch --show-current)"
```

On an existing file (resume), the script appends a `--- Resumed ---` marker instead of clobbering. All later writes — orchestrator and subagents — go through `${CLAUDE_PLUGIN_ROOT}/scripts/append-progress.sh`. Never `cat >>` the progress file directly. The progress file is throwaway telemetry in the temp dir (`${TMPDIR:-/tmp}` — macOS keeps `$TMPDIR` private per-user; see `prompts/progress.md`); it is not committed and not the resume state.

**Immediately after init, log the plugin version** as the first entry so the progress file is self-identifying (read `version` from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json`):

```bash
bash "${CLAUDE_PLUGIN_ROOT}/scripts/append-progress.sh" "${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt" "[orch] ralph v<version> — execute <single|wave>"
```

In wave mode, do this for each plan's progress file as W1 inits it.

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

Outer safety cap: **50 dispatches** total. The count is durable — the orchestrator increments `dispatches:` in the session manifest on every `ralph-task` dispatch (S1) and reads it back here, so the cap survives a resume. If `dispatches:` ≥ 50, stop and surface — the plan is too large or something is stuck.

### S1 — Dispatch next task

1. Find the first task with `[ ]` checkboxes.
2. Announce it to the user (task number + title + its `[ ]` items).
3. Dispatch `ralph-task` **in the background**:
   - `subagent_type: "ralph-task"`, `run_in_background: true`
   - Prompt includes: the full plan file, the single task as the target, the project CLAUDE.md, the contract text from `prompts/task.md`, **the progress file path**, and **the absolute path of `${CLAUDE_PLUGIN_ROOT}/scripts/append-progress.sh`** (resolve `${CLAUDE_PLUGIN_ROOT}` to its real path before passing — the subagent does not inherit the variable).
   - **Always** pass `RUN_PREFIX: <run_prefix>` (from the probe) so the task runs lint/typecheck/test:unit — and E2E — correctly on host or in-container.
   - **If `e2e: dev+prod` and single mode**: also pass `E2E_PER_TASK: on`, the resolved **dev-E2E command** (from pre-flight), and the **dev base URL**. These activate the task contract's "Dev-mode E2E variant" (`prompts/task.md`) — the task authors and runs its own spec instead of leaving a `FIXME(e2e)` placeholder. For `prod-only` / `unsupported` (and all wave tasks) pass nothing extra: the task keeps the default no-E2E contract.
4. Log: `append-progress.sh <progress-file> "[orch] dispatched ralph-task (sonnet) — Task N: <title>"`.
5. Record the task id as `running` in the session manifest and **increment its `dispatches:` counter** (the durable dispatch count the RECONCILE cap reads).
6. **End the turn** with a status line:
   > Task N/M dispatched in background. Session is free — ask "check progress" anytime. I'll continue automatically when it completes.

Do NOT wait. Do NOT poll. The harness re-invokes you on completion.

### S2 — Task verdict (on background completion)

1. Read the subagent's return summary and the **tail of the progress file**.
2. Re-read the plan. Are task N's `[ ]` boxes now `[x]` and is there a commit?
2a. **If the dispatch passed `E2E_PER_TASK: on`** (`e2e: dev+prod`, single mode): "green" additionally requires the task to report its dev-mode E2E spec **passed** — the relevant spec is implemented (not a `.skip` / `FIXME`) and committed. A task that reports `TASK_FAILED` because its spec would not go green is a normal failure → the retry / surface path (step 4) applies. Never mark a task green over a red or skipped E2E spec.
3. **Green** → `append-progress.sh <progress-file> "[orch] Task N — completed"`. Mark the task id `completed` in the manifest. Go to RECONCILE (which dispatches the next task).
4. **Not green / `TASK_FAILED`**:
   - **First failure** → `append-progress.sh <progress-file> "[orch] Task N — FAILED (retry 1)"`. Re-dispatch the same task in the background (S1 with a retry note in the prompt). End turn.
   - **Retry also failed** → `append-progress.sh <progress-file> "[orch] Task N — FAILED after retry"`. **Do NOT auto-advance.** Surface via AskUserQuestion (turn stays open for your decision):
     - "Edit plan and retry" — you revise the plan; restart that task with a fresh 2-attempt budget
     - "Skip task and continue" — mark `[~]` + `<!-- SKIPPED: <reason> -->`, continue
     - "Abort" — stop the run

**Per-task budget:** 2 background dispatches (1 + 1 retry). No more without user intervention.

### S-Status — on "check progress"

1. Read the tail (~30 lines) of `${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt`.
2. Summarize: current task, recent milestones, last timestamp.
3. **Flag circling explicitly** (per `prompts/progress.md`): same `validation: X FAIL` 3+ times, repeated `decision: revert`, or a long stale gap with no `DONE`.
4. If circling is detected, proactively offer: "this task looks stuck — want to pause and edit the plan?"
5. **Do not end the turn here.** Return to RECONCILE: if a completion is also pending it must still be processed (step 3); only when nothing else is pending does the turn end. The background agent keeps running either way.

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

### S3.5 — Full prod E2E gate (mandatory when E2E is available)

Skip **only** when `e2e: unsupported`. Otherwise, once the review loop exits clean, run the **full** E2E suite once against a **production build** — the mandatory acceptance gate before finalize:

```bash
<e2e_cmd>   # the probed entrypoint (env: block): "<run_prefix> bun run test:e2e" for a thin
            # runner, or host-side "bun run test:e2e" (NO run_prefix) when test:e2e self-orchestrates
            # container entry + host-side sidecars. Run it verbatim — do not re-prefix.
```

- Run the full suite **once** to catch cross-spec interactions and regressions. On failure: rerun **only failing suites** until green — **never** loop the whole suite (same rule as `/ralph e2e` Step 4).
- **Surfaced bugs are owned.** A failure in a spec this run didn't touch is a real bug — fix the underlying cause, do not `.skip` to green. If the fix is substantial (new design decision, schema migration, >30 lines), STOP and surface to the user as a new finding rather than scope-creeping.
- Log: `append-progress.sh <progress-file> "[orch] prod E2E gate — <pass | N failing suites>"`.
- Advance to S4 only once the suite is green, or the user explicitly overrides via AskUserQuestion (fix now / accept red / abort).

When `e2e: dev+prod` the per-task specs already passed in dev mode — this gate re-runs them (plus the rest of the suite) against the prod build to catch dev/prod divergence and regressions. When `e2e: prod-only` this is the first E2E run this session.

### S4 — Finalize

- Final lean validation (`lint && typecheck && test:unit`)
- Ensure all `[ ]` boxes are `[x]`
- Move the plan to `docs/plans/completed/`; commit the move
- `append-progress.sh <progress-file> "plan complete"` then append a `---` line and `Completed: <timestamp>`

### S5 — Handoff

**E2E status carries into the handoff.** If `e2e != unsupported`, the full prod E2E suite already passed in S3.5 — so `/ralph pr` can be created **hardened** without re-running E2E from scratch, and `/ralph e2e` is now audit-only (when `dev+prod`, every placeholder is already implemented). If `e2e: unsupported`, E2E never ran — PR is lean and carries the `FIXME(e2e)` note.

If `RALPH_AUTO_PR` is set:
- user said `"hardened"` / `"with review"` → chain into `/ralph review`
- otherwise → chain into `/ralph pr` (hardened if E2E passed this run, else lean)

Otherwise ask via AskUserQuestion:
- "Visual review (`/ralph review`)" (Recommended)
- "Create PR now (`/ralph pr`)" — hardened if E2E already passed this run (`e2e != unsupported`), else lean
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
grep -qxF '.ralph/' .gitignore 2>/dev/null || { printf '\n.ralph/\n' >> .gitignore && git add .gitignore && git commit -m "chore: ignore .ralph worktree dir"; }
```

(The leading `\n` in `printf` guards against a `.gitignore` whose last line has no trailing newline — without it the new entry would merge into the previous line. A blank line in `.gitignore` is harmless.)

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
2. Init the plan's progress file: `${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt` (flat temp-dir namespace — one place to read them all).
3. Dispatch the plan's **first** `[ ]` task as a background `ralph-task` (`run_in_background: true`), with the dispatch prompt carrying the **worktree root absolute path** plus everything from S1 step 3.
4. Record each plan's in-flight task id in the manifest's Execution Log.

All N first-tasks launch together — that is the parallelism.

### W-RECONCILE — multi-plan, runs at the top of every invocation

Same as single-mode RECONCILE, extended across plans — user message handled first so it is never dropped by a concurrent completion:

1. Re-read every active plan file.
2. **If the user sent a message** → handle it first: `pause` → stop all in-flight agents (S-Pause across plans), done; `check progress` → W-Status, then fall through; anything else → answer it, fall through if a completion is also pending else end turn.
3. **A background subagent completed** → identify which plan it belonged to (its task id is recorded per-plan in the manifest) → run W2 verdict for *that plan only*; the other plans keep running untouched.
4. For any plan with no in-flight agent and `[ ]` tasks remaining → dispatch its next task (W1 step 3, incrementing `dispatches:` — the 50-cap counts dispatches across all plans).
5. When every plan in the wave has all tasks `[x]` → W3.

### W2 — Per-plan task verdict

Identical to S2, scoped to the completed plan: green → log + advance that plan's next task; failed → one retry; retry failed → surface to user (that plan pauses, others continue).

### W-Status — on "check progress"

Read every plan's `${TMPDIR:-/tmp}/ralph-progress-<plan-stem>.txt` and summarize per plan: current task, recent milestones, circling flags. One compact block per plan.

### W3 — Wave transition

When all plans in the wave have every task `[x]`:
- Any plan ended failed/skipped → ask the user (fix and retry / accept / abort).
- All green → merge the wave's branches into the parent branch **one at a time** (sequential two-way merges, NOT an octopus merge — a single `git merge A B C` octopus aborts wholesale on any conflict and leaves no conflicted index to resolve):
  ```bash
  for b in ralph-<plan-stem-1> ralph-<plan-stem-2> …; do git merge --no-ff "$b" || break; done
  ```
  Parallel plans should be file-disjoint by design. If a merge does conflict, the loop stops on that branch and the repo is left mid-merge — **the orchestrator halts the wave here and surfaces the conflict to the user** (do not proceed to W4). Resume after the user resolves the conflict and commits.
- Advance to the next wave (back to W1).

### W4 — Merge wave

The final merge plan runs as a full **single-mode** loop (S1–S4, including the **S3.5 prod E2E gate** when `e2e != unsupported`) in its own worktree — tasks **and** the review loop. The git-diff-driven review covers the consolidated change surface; per-branch pre-merge review would produce false positives about missing wiring.

Per-wave plans run tasks-only; the merge plan runs the full pipeline. **In the current phase, per-task dev E2E is single-mode only** — per-wave tasks run lean validation, have no dev server, and leave `FIXME(e2e)` placeholders as usual; the consolidated prod E2E gate fires once here, on the merged surface. (Per-worktree-container wave E2E — each worktree running its own app via `worktree_isolation: docker-per-worktree` — is the planned follow-up.)

### W5 — Cleanup + handoff

- Set manifest `Current State: completed`
- `git worktree prune`; remove `.ralph/worktrees/*`
- Move the manifest to `docs/plans/completed/`
- Handoff per S5

## Resume

`/ralph execute resume` — read the manifest + plan checkboxes (the durable resume state), recreate any removed worktrees from their branches, re-init the progress file (the script appends a `--- Resumed ---` marker), and re-enter RECONCILE. Because resume state lives in the plan + manifest, resume works even if the old progress file is gone. Read the `env:` capability profile from the manifest instead of re-probing (re-probe only if the block is missing — e.g. an older manifest). Re-verify deps can still run (a cold-start worktree may have lost `node_modules`); and if `e2e: dev+prod` in single mode, re-resolve the dev-E2E command and re-ensure the warm dev server is up before dispatching the next task.
