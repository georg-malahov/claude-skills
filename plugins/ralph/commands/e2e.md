---
description: Ralph e2e — consume FIXME(e2e) placeholders and implement E2E tests one at a time.
argument-hint: '[file-or-glob]   (default: all FIXME(e2e) markers in tests/e2e/)'
---

# /ralph e2e

Runs **after** `/ralph review` has settled the UI. Hardens the result by turning every `FIXME(e2e)` placeholder into a passing E2E test. Separate skill, separate session — the main ralph loop never touches E2E.

## Session manifest

Create per dispatcher spec. `kind: e2e`. `artifact:` points at a worklist file `docs/plans/.scratch/e2e-worklist-<slug>.md` (created in Step 1). Checkpoint after the discovery scan, after each individual test goes green, and after the final full E2E run. Resume picks up from the next unstarted item in the worklist.

## Step 1 — Discover

```bash
grep -rn "FIXME(e2e" tests/e2e/ src/
```

Parse hits into a worklist: `{ file, line, scenario, kind (new|update|flaky), surrounding test.skip name }`.

If `$ARGUMENTS` filters to a file or glob, scope the worklist.

If a review dump exists (`docs/plans/.scratch/review-*.md`), cross-reference: surface any UI flows mentioned there that DON'T have a FIXME marker — those are gaps in the plan's E2E test plan. Ask the user whether to add them now (creates a new placeholder) or skip.

**Standalone fallback** — if no FIXME markers exist AND no review dump exists, this is an **audit mode** run. Treat the implicit ask as: "audit existing tests against the current implementation; find gaps, stale assertions, untested user-visible flows." Steps for audit mode:

1. List existing E2E tests: `find tests/e2e -name '*.spec.ts' -o -name '*.spec.tsx'`.
2. Dispatch a single audit Agent with: the list of routes/pages in the app (`src/app/**/page.tsx` and equivalents), the list of existing tests, and the contract: "find untested user-visible flows, find tests whose assertions are stale relative to current implementation, find tests that silently `.skip` without a FIXME marker."
3. The audit Agent outputs a worklist in the same shape as the FIXME-driven one (`{ file?, scenario, kind: audit-gap | audit-stale }`).
4. Present the worklist to the user and continue from Step 2 below.

Audit mode is the answer to "I ran `/ralph e2e` without anything pending — go check that what we have still matches reality."

## Step 2 — Plan the run

Present the worklist with counts. Ask via AskUserQuestion:
- header: "Scope"
- question: "Implement how many tests this session?"
- options:
  - "All" (Recommended if small) — go through the whole worklist
  - "First N" — implement the first N, leave the rest
  - "Pick interactively" — confirm each before starting

## Step 3 — Per-test loop

For each item:
1. Dispatch an Agent with:
   - The placeholder file + line
   - The scenario comment
   - The relevant route(s) + components under test
   - Contract: implement the test, run **only that single test file** (`bun run dx playwright test <file>` or project equivalent), iterate until green
2. On green: remove the `FIXME(e2e)` comment, change `test.skip` to `test`, commit (`e2e: <scenario>`).
3. On fail after 3 iterations: leave the placeholder, mark `FIXME(e2e, flaky): <reason>`, surface to user.

## Step 4 — Final full E2E run

Once all (or the chosen N) tests are green individually:
```bash
bun run dx bun run test:e2e   # or project equivalent
```

Run the **full** suite once to catch interactions. On failure: rerun only failing suites until green. **Never** loop the whole suite.

**Surfaced bugs are owned.** If the full E2E run fails in a test you didn't touch this session, fix the underlying bug — don't `.skip` the test to make the suite pass. Same rule as in `/ralph execute`: a bug surfaced is a bug owned. If the fix is substantial, stop and surface to the user as a new finding.

## Step 5 — Handoff

- Summarize: tests added, FIXMEs remaining
- If a PR exists: suggest updating its description with the new test count
- If no PR yet: suggest `/ralph pr` (hardened mode — full validation including E2E)
