---
description: Ralph PR — create a PR with selectable hardening level (lean vs hardened).
argument-hint: '[lean | hardened]   (default: ask, unless RALPH_AUTO_PR is set)'
---

# /ralph pr

Creates a GitHub PR for the current branch. Choice of two modes:

- **Lean** — gates on `lint + typecheck + test:unit` only. No E2E, no visual review prerequisite. Fast path for small fixes.
- **Hardened** — gates on full validation including `test:e2e`. Requires that `/ralph review` and `/ralph e2e` have been run.

## Step 0 — Prereqs

- `which gh` — must exist
- `git branch --show-current` — not main/master
- `git log <default>..HEAD --oneline` — must have commits

## Session manifest

Create per dispatcher spec. `kind: pr`. `artifact:` empty (PR is the side effect, not a file). Short manifest: checkpoint after mode selection, after gate passes, after PR is created. PR runs are usually fast — manifest is mainly useful when the validation gate fails and the user iterates.

## Step 1 — Mode selection

Parse `$ARGUMENTS`:
- `lean` → lean mode
- `hardened` → hardened mode
- empty:
  - If `RALPH_AUTO_PR` is set: default to **lean** mode unless the original user request also included `"hardened"` / `"with review"` / `"with e2e"` (then hardened).
  - Otherwise ask via AskUserQuestion:
    - header: "PR mode"
    - question: "How should this PR be gated?"
    - options:
      - "Lean (fast)" — lint + typecheck + unit only. For small fixes or when review/E2E will happen post-merge.
      - "Hardened (full)" (Recommended for feature branches) — full validation including E2E. Requires `/ralph review` + `/ralph e2e` already done.
      - "Cancel" — stop here

If hardened was selected but no review dump and no recent E2E commits exist: warn and ask whether to run `/ralph review` first or proceed anyway.

## Step 2 — Validation gate

**Lean mode:**
```bash
bun run lint && bun run typecheck && bun run test:unit
```
(prefix with `bun run dx` from host if dev container is present)

**Hardened mode:** the lean suite, then:
```bash
bun run test:e2e   # rerun only failing suites on iteration; never loop full suite
```

Order: cheapest first, fail-fast.

On failure:
- Surface failures
- Offer `/fix-to-green` (existing skill from `dev-workflow`) for actionable failures
- AskUserQuestion: Fix now and retry / Open as draft anyway / Stop

Do NOT proceed past this step on red, unless the user explicitly opted into draft.

## Step 3 — Build PR content

Run in parallel:
- `git log <default>..HEAD --oneline` — commit list
- `git diff <default>...HEAD --stat` — changed files
- Find a plan file: `$ARGUMENTS` path → branch-name match in `docs/plans/completed/` → none

**Title:** plan's `# ` line, or derive from branch + commits. Under 70 chars.

**Summary:** plan's `## Overview` section, or synthesize from commits.

**Test plan:**
- 3–6 SPECIFIC manual verification checkboxes derived from the actual diff
- No generic "all unit tests pass" — that's enforced by the gate
- If hardened: include "E2E suite green: <count> tests" line referencing the test files added
- If lean: include "E2E hardening deferred — see FIXME(e2e) markers in tests/e2e/"

**Demo:** if `/ralph demo` produced a hosted walkthrough for this branch this session (a recorded S3 URL, e.g. in the demo session manifest), add a `🎬 Demo` line to the body. Do not commit the video — link only.

**Review summary:** if `docs/plans/.scratch/review-<slug>.md` exists for this work, link or inline its Items section.

## Step 4 — Confirm

Unless `RALPH_AUTO_PR` is set, present title + summary + test plan and ask via AskUserQuestion:
- "Create PR" (Recommended)
- "Edit first"
- "Cancel"

With `RALPH_AUTO_PR`: skip confirmation.

## Step 5 — Create

```bash
git push origin HEAD -u    # if not already pushed
gh pr create --title "<title>" --base <default> --body "$(cat <<'EOF'
## Summary
<summary>

## Changes
<commit list>

## Test plan
<test-plan>

<review-summary if present>

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Report the PR URL.

## Step 6 — Cleanup (parallel orchestration only)

If a `*-execution.md` manifest existed (wave mode), ask whether to delete intermediate remote branches (`git push origin --delete ralph-<plan-stem>`). Skip if single-mode.

## Constraints

- Never PR against a red gate without explicit user opt-in.
- Never auto-create a PR unless `RALPH_AUTO_PR` was set at session start.
- Lean PRs explicitly carry a FIXME(e2e) deferral note in the test plan so reviewers know hardening is pending.
