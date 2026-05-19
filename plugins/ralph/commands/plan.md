---
description: Ralph plan — grill + auto-route single vs parallel; emit plan(s) and (if parallel) manifest.
argument-hint: '[description]   (also picks up brainstorm/review dumps automatically)'
---

# /ralph plan

Produces an implementation plan. Auto-decides whether to emit a single plan or a parallel DAG (waves + merge + manifest) based on the parallelism score.

## Step 1 — Seed

Collect all relevant context dumps from `docs/plans/.scratch/`:
- `brainstorm-*.md` — from `/ralph brainstorm`
- `review-*.md` — from `/ralph review` accumulate mode (treated identically to brainstorm dumps)

Concatenate any present dumps into the grill seed. If `$ARGUMENTS` is provided, prepend it.

If no dumps and no arguments: ask the user for a one-paragraph description, then continue.

## Session manifest

Create per dispatcher spec. `kind: plan`. `artifact:` initially empty; once the plan file (or manifest) is written, point it there. Checkpoint after grill question batches, after the routing decision, after each plan file is written, and after the execution manifest is written. If resuming, skip seeding (Step 1) and re-enter at the last checkpoint.

## Step 2 — Grill (interview-driven)

Invoke the `interview` skill with the grill framing — same probes as `/orchestrate plan` Step P1, distilled here:

- What are the distinct work streams?
- For each pair: do they depend on each other or are they independent?
- What shared foundation (schema, layout, services) must exist before parallel work?
- What integration points need a merge step?
- Any new npm/bun deps? (If yes → flag as BEFORE-LAUNCH item.)

Ask one question at a time. Recommend an answer. Explore the codebase instead of asking when answerable.

## Step 3 — Parallelism scoring

After grilling, compute:
- `streams` = count of distinct work streams identified
- `independent_pairs` = count of (i, j) stream pairs with no dependency
- `mock_feasible` = boolean — can sibling outputs be mocked with reasonable cost?

Routing:
- **Parallel mode** if `streams >= 3` AND `independent_pairs >= 2` AND `mock_feasible`
- **Single mode** if `streams <= 2` OR everything is strictly sequential
- **Ambiguous** → present the DAG sketch and ask via AskUserQuestion (recommend the more conservative single mode unless the user wants parallelism)

## Step 4a — Single mode

Write one plan to `docs/plans/YYYY-MM-DD-<slug>.md`:

```markdown
# <Title>

## Overview
<what this delivers and why>

## Context
<grilled context, scoped to this work>

## Development Approach
- Testing: TDD preferred; every task includes unit tests
- E2E: deferred — leave FIXME(e2e) placeholders for user-visible behavior
- Validation: lean (lint + typecheck + test:unit) per task

## Implementation Steps

### Task 1: <name>
- [ ] <action>
- [ ] write unit tests
- [ ] FIXME(e2e) placeholder if user-visible
- [ ] run lean validation

### Task N: Verify
- [ ] confirm requirements met
- [ ] final lean validation
```

No manifest needed. Tell user: `/ralph execute` to run it.

## Step 4b — Parallel mode

Mirror the `/orchestrate plan` Steps P2–P5 logic:

1. **Decompose** into waves (foundation → parallel tracks → sequential follow-ups → merge wave).
2. **Validate** plan sizes (3–6 tasks each) and challenge dependencies — can they be eliminated with mocks?
3. **Generate per-wave lean plans** using parallel Agent instances. Each plan declares Mocks (removed during merge).
4. **Generate the merge plan** at `docs/plans/YYYY-MM-DD-<feature>-merge.md`. Tasks: manifest cross-check, mock removal, component wiring, full validation **minus E2E** (E2E still excluded — that's `/ralph e2e`'s job), update docs.
5. **Write the execution manifest** at `docs/plans/YYYY-MM-DD-<feature>-execution.md` with the DAG and an empty execution log table.

If the grill surfaced new npm/bun deps: each plan's Context block has a `### BEFORE LAUNCH (host)` section listing packages. `/ralph execute` will gate on this.

## Step 5 — Handoff

Summarize what was created. Suggest `/ralph execute` next.

If `RALPH_AUTO_PR` is set (autonomous mode), chain directly into `/ralph execute` without waiting.
