---
description: Ralph fix — turn multiple bug reports/observations into committed test-first fixes.
argument-hint: 'free text describing one or more bugs/observations, or attached screenshot'
---

# /ralph fix — Test-First Multi-Bug Squashing

Take one or many bug reports, observations, code-review comments, or QA notes at once. Categorize each. For real bugs, follow a test-first loop: write a failing test, commit it, write the fix, commit the fix. For non-bug items, apply lighter handling.

Do **not** open a PR at the end. `/ralph pr` is a separate explicit step (it has its own validation gate).

## Session manifest

Create per dispatcher spec (`commands/ralph.md` → "Session manifests"). `kind: fix`. `artifact:` empty (the commits are the output, not a file). Checkpoint after intake confirmation, after the categorization is confirmed, and after each item's fix commit, so an interrupted multi-bug run can be resumed without re-asking.

## Step 0: Intake

`$ARGUMENTS` is the user's input. It may be:
- A single bug description ("the calendar shows the wrong week on Monday at 00:00")
- A batch of comments pasted from a code review or QA session (multiple bullets)
- A screenshot reference + text
- Empty — ask the user for their observations via plain chat

**Echo back what you parsed** as a numbered list of items. Confirm: "Got these N items right?" before moving on.

## Step 1: Categorize

For each item, assign one category:

| Category | Definition |
|----------|-----------|
| `bug` | Reproducible incorrect behavior — needs a failing test + fix |
| `refactor` | Code-smell / structure change with no behavior delta |
| `doc` | Documentation, comments, README, or copy updates |
| `chore` | Dependency bumps, config tweaks, formatting, tooling |
| `defer` | Real but out of scope for this session |
| `unclear` | Need more info from the user before acting |

Use AskUserQuestion only if a category is ambiguous. For obvious cases, just decide and present the categorization table for confirmation:

```
1. [bug]      Calendar Monday-00:00 off-by-one
2. [refactor] Extract availability-check helper from termin-service
3. [doc]      Update README — new dev container command
4. [chore]    Bump zod 4.2 → 4.3
5. [unclear]  "Patient form looks weird on mobile" — needs a screenshot or steps
```

Ask the user to confirm or adjust. Park `unclear` items by asking follow-up questions. Drop `defer` items (note them for later).

## Step 2: Plan Execution Order

Order matters for clean history:

1. **Bugs first**, one at a time (each gets a failing-test commit + fix commit pair)
2. **Refactors** second (single commit each, no test-first)
3. **Chores** third (single commit each)
4. **Docs** last (single commit each, or grouped if related)

Show the planned commit sequence to the user and confirm.

## Step 3: Execute Bug Items (test-first loop)

For each `bug` item:

### 3.1 Reproduce — Write a failing test

- Pick the right test layer:
  - Pure logic → unit test (Vitest, co-located `.test.ts`)
  - User flow / UI → E2E test (Playwright `tests/e2e/*.spec.ts`)
- Pin determinism: timezones, dates, random seeds, browser viewports if relevant
- Write a test that **reproduces the bug** — assert the correct behavior, which will currently fail

### 3.2 Confirm red

Run only that test:
- Unit: `bun run test:unit -- <file>` (or project equivalent)
- E2E: target the single spec — `bun run test:e2e <file>` (or `bun run dx bun run test:e2e <file>` from host with dev container)

Verify the failure is **for the right reason** (the assertion you wrote), not a setup error. If the test errors out in setup, fix the test before continuing.

### 3.3 Commit the failing test

```bash
git add <test-file>
git commit -m "test: reproduce <bug summary>"
```

The failing-test commit is intentionally preserved in history — it documents the bug and proves the fix works.

### 3.4 Iterate to green

Loop (max ~10 iterations):
- Edit code to fix
- Rerun only the targeted test (per-file/per-suite, not full suite)
- If green: break
- If still red: refine

**Refuse to weaken assertions.** If the test seems impossible to satisfy, that's a signal the original bug report or the assertion was wrong — go back and re-discuss with the user, don't just delete the test.

### 3.5 Commit the fix

```bash
git add <changed-files>
git commit -m "fix: <bug summary>"
```

### 3.6 Regression check (lightweight, per-bug)

After each bug fix, run the cheap stages of validation: `lint + typecheck + test:unit`. If anything new breaks, fix it without touching the original assertion (those failures are regression candidates, not assertion problems).

Do NOT run E2E after every bug — too expensive. E2E runs once at the end (Step 5).

## Step 4: Execute Non-Bug Items

For each `refactor` / `chore` / `doc` item:

- Make the change
- Commit with appropriate conventional prefix (`refactor:`, `chore:`, `docs:`)
- No test-first requirement, but:
  - If a refactor accidentally changes behavior, that's a bug — convert it to a bug item and follow Step 3
  - Refactors must not lower test coverage

## Step 5: Final Full Validation

Once all items are addressed, run the **full project validation suite** (see user-level CLAUDE.md "Run validation"):

```bash
# In a container:
bun run lint && bun run typecheck && bun run test:unit && bun run test:e2e

# From host with dev container:
bun run dx bun run lint && bun run dx bun run typecheck && \
  bun run dx bun run test:unit && bun run dx bun run test:e2e
```

**E2E iteration policy**: if a spec other than the ones modified fails, that's a regression introduced by your changes — go back, fix, re-run only that spec, then proceed. Do not re-run the full E2E suite after each per-spec fix.

## Step 6: Report

Summarize what was done:
- Items handled (by category)
- Commits created (with messages)
- Items deferred or unresolved
- Validation status
- Reminder: "Run `/ralph pr` when ready to open a PR — it has its own validation gate."

Do **not** auto-open the PR. That's explicit, separate, and gated.

## Constraints

- One bug at a time during Step 3 — keep commits clean
- Failing-test commit + fix commit are **two separate commits in the same branch/PR** — never split into separate PRs
- Refuse to weaken or delete assertions to make a test pass; instead re-discuss with the user
- No test-first for refactor/chore/doc items
- E2E only at the end (full sweep), or per-spec when iterating a specific E2E-targeted bug
