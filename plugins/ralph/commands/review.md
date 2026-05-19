---
description: Ralph review — manual visual Q&A via `interview`. Two modes: accumulate or fix-now.
argument-hint: '[accumulate | fix-now]'
---

# /ralph review

Drives a manual walkthrough of the changes since the default branch, using the `interview` skill. Two modes; you can switch mid-session.

## Step 1 — Mode selection

Parse `$ARGUMENTS`. If a mode is supplied, use it. Otherwise ask via AskUserQuestion:
- header: "Mode"
- question: "How are we reviewing?"
- options:
  - "Accumulate" (Recommended for non-trivial changes) — log comments to a review dump that `/ralph plan` will pick up as a follow-up seed. No code edits during the session.
  - "Fix-now" — each comment becomes an immediate small edit, validated and committed inline. Good for typos, copy, spacing.

The user can say "switch to accumulate" / "switch to fix-now" mid-session.

## Session manifest

Create per dispatcher spec. `kind: review`. `artifact:` points at the review dump path (accumulate mode) or is empty (fix-now mode — each fix is its own commit). Checkpoint after each section is walked. Critically for accumulate mode: each user comment is written to the dump file AND the checkpoint log immediately — that way a Ctrl+C in the middle of the walk leaves a usable partial dump that can be continued next session.

## Step 2 — Build the walkthrough surface

Gather what to walk through:
- `git diff <default-branch>...HEAD --stat` for the file list — works whether or not there's any prior ralph context
- Group files into logical sections (route/page, schema, components, services, tests)
- For each section, prepare a short framing: what changed, why, what to verify in the UI

**Standalone fallback** — if invoked with no prior execute context (no recent plan, no manifest, no review dump): treat the entire diff against `<default-branch>` as the review surface. The implicit ask is "walk me through recent changes that aren't yet reviewed." Do not require a plan file to exist.

If a `/preview-check` report exists in `docs/previews/`, surface its screenshots inline.

## Step 3 — Interview loop

Invoke the `interview` skill with the framing:

> Manual visual review. We'll walk section by section. For each section I'll summarize what changed; you tell me what you see in the UI / what's off. Recommend `looks good` / `note` / `fix` for each section.

For each section:
1. Summarize the change.
2. Ask one open question: "How does this look? Anything off?"
3. Record the answer.
4. If **accumulate mode**: append to dump.
5. If **fix-now mode** AND the answer implies a fix: dispatch a small Agent to make the edit + run lean validation + commit. Show the diff. Continue.

## Step 4a — Accumulate output

Write the dump to:
```
docs/plans/.scratch/review-<slug>.md
```

Format:
```markdown
# Review: <feature>
Date: <YYYY-MM-DD>
Branch: <branch>

## Summary
<one-paragraph synthesis of what needs follow-up>

## Items
### <section name>
- **Status:** note | fix-needed
- **Observation:** <user's comment>
- **Suggested action:** <one line>

## Raw interview log
<verbatim Q&A>
```

Tell the user:
> Review saved to `docs/plans/.scratch/review-<slug>.md`. Run `/ralph plan` next — it will pick this up as the grill seed for the follow-up.

## Step 4b — Fix-now output

After the walkthrough:
- Summarize commits made
- Run lean validation one final time end-to-end
- Suggest `/ralph pr` (or chain into it if `RALPH_AUTO_PR` is set)

## Notes

- Never run E2E here. E2E is a separate phase.
- Never combine the modes silently — if the user asks for a fix during accumulate mode, ask whether to switch modes or just log it.
