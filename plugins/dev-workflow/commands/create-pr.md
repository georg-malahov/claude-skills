---
description: Create a GitHub PR for the current branch, gated on green validation
argument-hint: 'optional plan file path'
---

# Create Pull Request

Create a GitHub pull request for the current branch with a structured summary, test plan, and **validation gating** — refuses to open the PR until the full project validation suite is green.

## Step 0: Verify Prerequisites

1. Check `gh` CLI is available: `which gh`
   - If not found, inform user and stop.

2. Check current branch is not main/master:
   - Run: `git branch --show-current`
   - If on main/master, inform user and stop.

3. Check there are commits ahead of the default branch:
   - Determine default branch: try `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` (fallback: `main`)
   - Run: `git log <default>..HEAD --oneline`
   - If no commits, inform user and stop.

## Step 1: Gate on Green Validation

**This is the gate. Do NOT proceed to PR creation if validation is not green.**

Run the project's full validation suite — see user-level CLAUDE.md ("Run validation") for what that means. For a typical Bun + Next.js + Playwright project:

- Inside a container / ralphex: run directly
  ```bash
  bun run lint && bun run typecheck && bun run test:unit && bun run test:e2e
  ```
- From the host with a dev container present: prefix with `bun run dx`
  ```bash
  bun run dx bun run lint && bun run dx bun run typecheck && \
    bun run dx bun run test:unit && bun run dx bun run test:e2e
  ```

**Order matters — cheapest first. Stop on first failure and report.** Do not keep running once one stage is red.

**E2E specifics:**
- E2E runs are heavy. Run against the project's dedicated E2E dev server / container, not an arbitrary running instance.
- **On failure: rerun only failing test files / suites during fix iterations** — do NOT re-run the full E2E suite after each code change. Identify failing specs (e.g. `tests/e2e/foo.spec.ts:42:1 — flow X`), iterate on them, and only do a full re-run once they're green individually.

**If validation fails:**
- Surface the failure to the user. Do NOT auto-open the PR.
- Offer to invoke `/fix-to-green` if there are concrete failures to address.
- Ask the user how to proceed via AskUserQuestion:
  - "Fix now and retry" — wait for fixes, then re-run validation
  - "Open PR as draft anyway" — only if user explicitly opts in (rare)
  - "Stop" — abort PR creation

**Only proceed past this step if all validation is green or the user explicitly bypasses.**

## Step 2: Gather Context

Run these in parallel:

1. `git log <default>..HEAD --oneline` — commit list
2. `git diff <default>...HEAD --stat` — changed files summary
3. Check if a plan file is referenced:
   - If `$ARGUMENTS` contains a plan file path, use that
   - Otherwise, check `docs/plans/` for a plan matching the current branch name
   - If no plan found, proceed without one

## Step 3: Build PR Content

**Title:**
- If plan file exists: extract from the first `# ` line (strip prefix), keep under 70 characters
- If no plan: derive from branch name and commit messages, keep under 70 characters

**Summary:**
- If plan file exists: extract the `## Overview` section
- If no plan: summarize the changes from commit messages and diff stat

**Test plan:**
Generate a SPECIFIC test plan based on the actual changes:
- Read the diff stat and commit messages to understand what was changed
- Write 3-6 checkbox items describing concrete verification steps
- Each item must be actionable (e.g., "Open /dashboard and verify the new tab loads with sample data")
- Do NOT use generic items like "All unit tests pass" — those are enforced by the gate above
- Focus on manual verification, behavioral checks, integration testing specific to the changes

**Screenshots / preview:**
If a `/preview-check` report exists in this branch (e.g. `docs/previews/`), reference it in the PR body. Otherwise, skip.

## Step 4: Confirm with User

Present the PR title, summary, and test plan. Use AskUserQuestion:
- header: "PR"
- question: "Create this pull request?"
- options:
  - "Create PR" — proceed
  - "Edit first" — let user modify before creating

If user wants to edit, ask what to change and update accordingly.

## Step 5: Create PR

```bash
gh pr create --title "<title>" --base <default> --body "$(cat <<'EOF'
## Summary
<summary>

## Changes
<commit list>

## Test plan
<test-plan>

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Report the PR URL when done.

## Step 6: Clean Up Remote Branches (optional)

After PR creation, check for intermediate backup branches on GitHub from orchestrated runs.

1. List remote branches that were part of this orchestration:
   - Look at the execution manifest (`docs/plans/*-execution.md`) for branch names
   - Or check `git branch -r` for branches matching the plan names
2. If intermediate branches exist, ask the user:
   - header: "Cleanup"
   - question: "Delete intermediate remote branches from GitHub?"
   - options:
     - "Delete all" — remove all intermediate backup branches from remote
     - "Keep them" — leave as-is
3. If user approves, delete each: `git push origin --delete <branch-name>`
4. Local branches and worktrees are NOT deleted here — they are managed by ralphex and git

## Constraints

- **Never create a PR against a branch with failing validation.** The Step 1 gate is the enforcement point — only the user can override, explicitly.
- Always confirm with user before creating PR and before deleting remote branches
- If the branch has not been pushed, push it first: `git push origin HEAD -u`
- If `gh pr create` fails with a TLS/certificate error, retry with `dangerouslyDisableSandbox: true` — the sandbox network restrictions can block GitHub API calls
- Reopening a closed PR follows the same gate: validation must be green first, then `gh pr reopen` + `gh pr edit` for updates
