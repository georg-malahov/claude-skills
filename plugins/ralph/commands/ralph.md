---
description: Ralph — native agentic loop. Dispatches to brainstorm | plan | execute | review | e2e | pr | demo.
argument-hint: '<subcommand> [args]   (brainstorm | plan | execute | review | e2e | pr | demo)'
---

# /ralph — dispatcher

Single entry point for the full ralph workflow. Parse `$ARGUMENTS`: first token decides the subcommand. Remaining tokens are forwarded.

## Version banner — print first, every run

Before routing, read `version` from `${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json` and print one line so the run is self-identifying:

```
ralph v<version> — <subcommand>
```

`bash -c 'grep -m1 '"'"'"version"'"'"' "${CLAUDE_PLUGIN_ROOT}/.claude-plugin/plugin.json"'` works in one call. This matters because plugin files are loaded once at session start — a session that loaded an older plugin keeps running it even after the marketplace is updated, and the version is the only reliable way to tell which behavior is live. If `${CLAUDE_PLUGIN_ROOT}` is unset, say so explicitly: that means ralph is not running as an installed plugin (loose files), which is itself worth surfacing.

`/ralph execute` additionally writes the version as the first logged line of every progress file (see `commands/execute.md` Step 1), so progress files are self-identifying too.

## Subcommands

| Subcommand | File | Purpose |
|---|---|---|
| `brainstorm` | `commands/brainstorm.md` | Interview-driven context gathering. Output → `docs/plans/.scratch/brainstorm-*.md` |
| `plan` | `commands/plan.md` | Grill + auto-route single vs parallel; emit plan(s) and (if parallel) manifest |
| `execute` | `commands/execute.md` | Run the native ralph-loop. Auto-detects single-plan vs wave mode from manifest |
| `review` | `commands/review.md` | Manual visual Q&A via `interview`, two modes (accumulate / fix-now) |
| `e2e` | `commands/e2e.md` | Consume `FIXME(e2e)` placeholders; implement E2E tests one at a time |
| `pr` | `commands/pr.md` | Create a PR; choose hardening level (lean / hardened) |
| `demo` | `commands/demo.md` | Auto-generate a narrated walkthrough video (screenplay → TTS → paced capture → mux); host on S3; attach to the PR |

## Session manifests — resumability

Every subcommand creates and maintains a **session manifest** so any session can be paused (intentionally or by interruption) and resumed in a future session without losing intent.

### Manifest location and format

One file per session at `docs/plans/.scratch/session-<YYYY-MM-DD-HHmm>-<slug>.md`:

```markdown
---
kind: brainstorm | plan | execute | review | e2e | pr
status: in_progress | completed | abandoned
started: <ISO timestamp>
updated: <ISO timestamp>
artifact: <relative path to the working file, or empty>
parent: <relative path to a parent session manifest, or empty>
---

# Intent
<one line — the user's original ask, verbatim if short, paraphrased otherwise>

# Arguments
<the $ARGUMENTS string for this subcommand invocation>

# Checkpoint log
- <ISO>: <step description>
- <ISO>: <step description>
```

### Required behavior in every subcommand

**At start (before any work):**

1. Scan `docs/plans/.scratch/session-*.md` (sorted by `updated` desc).
2. For each manifest with `status: in_progress`:
   - **Same kind as current invocation** → offer via AskUserQuestion:
     - "Resume this session" (Recommended — describe the intent + last checkpoint)
     - "Start new (mark this one abandoned)"
     - "Cancel"
   - **Different kind, but its artifact is still mid-flight** (e.g. a `brainstorm` in_progress when user runs `/ralph plan`) → surface it as context: "There's an in-progress `<kind>` session: <intent>. Resume that first?" with options Resume / Continue with current command / Cancel.
3. If user starts new (or there's nothing in progress) → create a fresh manifest file with `status: in_progress`, `started` = now, `updated` = now, `artifact` pointing at whatever working file the subcommand will write to.

**During work:**

After each meaningful checkpoint (one question batch finished in `interview`, one task completed in `execute`, one review iteration done, etc.):
- Append a line to `# Checkpoint log` with timestamp + one-line description.
- Update the `updated:` frontmatter timestamp.

These updates should be cheap — a single Edit per checkpoint. Don't batch.

**On normal completion:**

- Set `status: completed`. Update `updated:`.
- Add a final checkpoint: `- <ISO>: completed`.

**On user pause / Ctrl+C / abort:**

- Leave `status: in_progress` so the next session can find and resume it.
- Add a final checkpoint: `- <ISO>: paused by user` (or similar).

**On explicit abandon (user chose "Start new"):**

- Set `status: abandoned`. Update `updated:`.
- Do not delete — the manifest is a record of what was attempted.

### Why this exists

The default Claude-Code session has no durable memory. Without these manifests:
- A `brainstorm` interrupted at question 7 is lost on the next session.
- A `review` accumulate mode interrupted mid-walk leaves orphan comments.
- An `execute` interrupted between waves can be picked up by `resume`, but standalone subcommands (brainstorm, plan, review, e2e, pr) have no equivalent.

Manifests fix that uniformly. They are also the answer to "what did I leave half-done last week?" — `ls docs/plans/.scratch/session-*.md | xargs grep -l 'in_progress'` is the answer.

### Cleanup

Manifests live in `.scratch/` and accumulate. Periodically (no automated trigger): the user runs `/ralph` with no args, the dispatcher offers to archive `completed` and `abandoned` manifests older than 30 days into `docs/plans/.scratch/archive/`.

## Routing

1. If `$ARGUMENTS` is empty or unrecognized, infer state and propose the next step:
   - No `docs/plans/.scratch/brainstorm-*.md`, no plans → suggest `brainstorm`
   - Brainstorm dump exists, no plans → suggest `plan`
   - Plan(s) exist, no `Current State: completed` in manifest (or single plan has unchecked boxes) → suggest `execute`
   - Execute complete, no `docs/plans/.scratch/review-*.md` → suggest `review`
   - Review accumulate dump exists → suggest `plan` (it will be picked up as seed)
   - All boxes checked, no PR → suggest `pr`
   - PR exists, no demo attached for this branch → suggest `demo` (the visual companion; optional)
   Use AskUserQuestion with the inferred next step as the first (recommended) option.

   Plus: scan in-progress session manifests first (see "Session manifests" above) and surface them before suggesting a fresh action.

2. **Autonomous mode flag.** If the user's original request contains a phrase like `"implement autonomously and create pull request"` (or `"autonomous + PR"`, `"go end-to-end"`), set `RALPH_AUTO_PR=true` in the session context. Subcommands check this flag:
   - `execute` does not stop to ask after finishing; it chains directly into `review` only if the user also said `"with review"` or `"hardened"`, otherwise chains directly into `pr` in lean mode.
   - `pr` does not ask for confirmation when `RALPH_AUTO_PR` is set — it proceeds, still gated on green lean validation.

3. Forward control to the chosen subcommand file by reading it and following its instructions inline. Each subcommand is self-contained.

## Hard rules across all subcommands

- **Subcommands are independent.** Each one reuses prior step output if present, runs cleanly from scratch otherwise. See each subcommand's "standalone fallback" section.
- **Surfaced bugs are owned.** If validation (lean or E2E) surfaces a bug in code outside the current change, fix it. Exception: if the fix is substantial (new design decision, >30 lines, schema migration), surface to user instead of silently scoping in.
- **E2E is capability-gated and mandatory when available — no mode menu.** The `/ralph execute` environment probe (Step 1) detects whether the project can run E2E. If it can: per-task dev-mode E2E (single mode) **and** a full prod-build gate after the review loop, both mandatory. If it can't (`e2e: unsupported`): lean-only, automatically. See `commands/execute.md` → "Environment & capability probe".
- **Lean validation** = `lint → typecheck → test:unit`, run through the probed `run_prefix` (empty on host, `bun run dx` in-container). Full E2E (`test:e2e`) runs inside `/ralph e2e`, inside `pr` hardened mode, and — whenever E2E is available — as the mandatory post-review gate (S3.5) in `/ralph execute`.
- **Never auto-create a PR** unless the user opted in via the autonomous-mode phrase (rule 2).
- **Three-tier override chain** for agents and prompts: `.claude/ralph/{agents,prompts}/<name>.md` (project) → `${CLAUDE_PLUGIN_ROOT}/agents,prompts/<name>.md` (bundled) → fail loud.
- Coexists with `/orchestrate` and `/create-pr` — do not call them; ralph is a parallel track.
