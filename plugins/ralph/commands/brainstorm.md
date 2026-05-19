---
description: Ralph brainstorm — interview-driven context gathering, output feeds /ralph plan.
argument-hint: '[topic or feature description]'
---

# /ralph brainstorm

Open-ended divergent context gathering. Driven by the `interview` skill — one question at a time, running log, summary at end.

## Step 1 — Seed

1. Parse `$ARGUMENTS` for the topic. If empty, ask: "What are we brainstorming?"
2. Launch the `Explore` agent in parallel to gather repo context relevant to the topic (existing models, related features, current patterns). Cap at one focused sweep — this is divergent thinking, not architectural archaeology.

## Session manifest

Before Step 2: create the session manifest per the dispatcher's spec (`commands/ralph.md` → "Session manifests"). Set `kind: brainstorm`, `artifact:` pointing at the eventual dump path. If an in-progress brainstorm session was found and the user chose to resume, **skip Step 1 seeding** and pick up from the last checkpoint instead.

Checkpoint after each question/answer pair, after the Explore sweep returns, and on dump-write. Each checkpoint is a one-line append to `# Checkpoint log` plus an `updated:` bump.

## Step 2 — Interview loop

Invoke the `interview` skill with the following framing:

> Brainstorming session for: **<topic>**. Goal: surface goals, constraints, users, success criteria, non-goals, and any prior art in the repo. Walk through one question at a time. Recommend an answer to every question. Probe assumptions ("why", "what if", "what's the smallest version"). Avoid solutioning — gather context.

Suggested question arcs (the interview skill decides cadence and order):
- **Goals** — what does success look like in one sentence?
- **Users** — who triggers this, who consumes the output?
- **Constraints** — deadlines, dependencies, things that must not change?
- **Non-goals** — what is explicitly out of scope?
- **Prior art** — what in the codebase is the closest analog?
- **Risk** — what's the single thing most likely to go wrong?

## Step 3 — Output

When the interview ends, write the dump to:

```
docs/plans/.scratch/brainstorm-<slug>.md
```

Format:

```markdown
# Brainstorm: <topic>
Date: <YYYY-MM-DD>

## Summary
<one paragraph synthesis>

## Goals
- ...

## Non-goals
- ...

## Constraints
- ...

## Open questions
- ...

## Repo context
<from the Explore sweep>

## Raw interview log
<verbatim Q&A from the interview skill>
```

## Step 4 — Handoff

Tell the user:
> Brainstorm saved to `docs/plans/.scratch/brainstorm-<slug>.md`. Run `/ralph plan` next — it will pick this up automatically as the grill seed.

Do NOT auto-launch `/ralph plan`. Brainstorm is a pure context phase; the user decides when to move on.
