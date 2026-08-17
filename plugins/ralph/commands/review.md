---
description: Ralph review — browser-driven visual walkthrough. The agent verifies in the running app BEFORE concluding; the human is consulted only where judgement is needed.
argument-hint: '[accumulate | fix-now | prepare-ui] [what to look at]'
---

# /ralph review

Walks the changes since the default branch **in the running application**. The
agent drives the browser, reproduces each claim, and only then reports.

The old shape of this command — describe a change, ask the human what they see,
write down the answer — put the human in the loop for every step, including the
ones with an objectively checkable answer. Anything the agent can check, the
agent checks. What is left for the human is what actually needs a person:
whether something is *right*, not whether it is *there*.

## Step 0 — Preview up, and provably current

**Do this before anything else, and never skip the freshness check.** A stale
build is the single largest source of defects that do not exist — findings get
written up, argued about, and only then traced to a server serving last week's
code.

1. Start the preview (`preview_start` with the project's dev-server entry, or a
   `url` for an already-running app). Never start a dev server with a raw shell
   command.
2. **Prove the build is current.** Change something observable — or check a
   marker you know landed in this branch — and confirm the page reflects it. If
   it does not, restart the dev server and clear its build cache before going
   further.
3. Note in the manifest which build you are reviewing (commit SHA + how you
   verified freshness). Every finding is only as trustworthy as this line.

Known traps, all of which have produced phantom defects before:

- **A warm dev server serves stale compiled routes.** It may rebuild neither on
  edit nor on request. A server-side fix appears to have no effect.
- **An E2E production build clobbers `.next`.** If an E2E run happened while the
  dev server was up, the app renders but does not hydrate: *every* control is
  dead, not just the one you are looking at. Test a known-good control (a theme
  toggle) to tell environmental breakage from a component bug.
- **A fresh container has no seeded user.** Sign up first. Use the demo prefill
  button ("Ausfüllen") rather than typing credentials.
- **Synthetic pointer events may not reach React.** If a click through the
  automation layer fires no handler, retry with a real DOM `.click()` via the
  JavaScript tool before concluding the control is broken.

## Step 1 — Mode

Parse `$ARGUMENTS`. If a mode is given, use it. Otherwise ask via
AskUserQuestion:

- **Accumulate** (recommended for non-trivial changes) — verify everything, log
  findings to a review dump that `/ralph plan` picks up as a seed. No code edits.
- **Fix-now** — each confirmed finding becomes an immediate small edit,
  validated and committed inline. Good for copy, spacing, obvious slips.
- **Prepare-UI** — do not review; *stage* the app so a human can check one
  specific thing in one glance. See Step 5.

The user can switch modes mid-session.

## Session manifest

Create per dispatcher spec. `kind: review`. `artifact:` points at the review
dump (accumulate) or is empty (fix-now). Record the reviewed build SHA and the
freshness check from Step 0. Checkpoint after each section, and write every
finding to the dump **as it is confirmed** — a Ctrl+C mid-walk must leave a
usable partial dump.

## Step 2 — Build the walkthrough surface

- `git diff <default-branch>...HEAD --stat` for the file list.
- Group into sections (route/page, schema, components, services).
- For each section write down, before opening the browser: **what changed, and
  what would be observably true if it works.** A section whose expected
  observation you cannot state is a section you cannot verify — say so instead
  of inventing one.

**Standalone fallback** — with no prior execute context, treat the whole diff
against `<default-branch>` as the surface. Do not require a plan file.

## Step 3 — Verify it yourself

**This is the step that replaced asking the human.** For each section:

1. Navigate to the surface and put it in the state the change concerns. Creating
   that state is usually most of the work — a case at the right stage, a slot in
   the right status, an invoice with the right history. Set it up through the
   app's own API where clicking would take twenty steps.
2. Observe. Prefer `read_page` and page text over screenshots for anything
   textual — it is faster and it quotes exactly.
3. Compare against the expected observation from Step 2.
4. Record a verdict with evidence attached:

| Verdict | Means |
|---|---|
| **holds** | Observed doing what it claims. Quote the text or attribute you saw. |
| **defect** | Observed failing. Include the reproduction: URL, state, action, what happened instead. |
| **not reproduced** | Tried and could not make it happen. **State what you tried** — this verdict is worthless without it. |
| **blocked** | Could not reach the state. Say what stopped you. Never silently downgrade this to "holds". |
| **contested** | Works as built, but whether that is *right* is a judgement call. → Step 4. |

### Measure, do not argue

When something does not behave as expected, the temptation is to read the code
again and reason harder. Reading the code twice has produced confident, wrong
answers; a single measurement has settled the same question in a minute. Reach
for the cheapest probe that produces a fact:

- **`document.elementFromPoint(x, y)`** at the centre of a control that "does
  not respond" — it names what is actually under the cursor. Overlays, fixed
  docks and nested buttons are invisible in source and obvious here.
- **Bounding rects** of the element, its container, and the viewport — layout
  collisions become arithmetic instead of opinion.
- **The database.** A value the UI disputes is one query away. "The UI says
  unread" and "the row says read" are different findings with different fixes.
- **The API response.** Dump the endpoint the surface reads. It separates a
  render bug from a data bug in one call.
- **Console and network** (`read_console_messages`, `read_network_requests`) —
  a silent failure usually is not silent there.

A finding written without one of these is a hypothesis. Label it as one.

### Before filing anything based on absence

"X does not happen" is the claim most often wrong. Rule out, in order: the stale
build (Step 0), a click that never reached the handler, a state you did not
actually reach, and a selector matching a different element. Only then file it.

## Step 4 — Bring in the human, sparingly

Invoke the `interview` skill **only** for items marked `contested`, plus
anything genuinely ambiguous. Framing:

> These work as built; whether they are right is your call. For each I will show
> what I observed and the trade-off, then take your decision.

Per item: what was observed (with evidence), what the alternatives are, and a
recommendation. The human decides; the agent does not re-litigate afterwards.

Everything already verified is reported, not asked about. If the whole walk
produced nothing contested, do not open an interview at all — say so and hand
over the results.

## Step 5 — Prepare-UI mode

The ask is: *"set the app up so I can look at this one fix."* Getting to the
right screen is often many steps and easy to get subtly wrong, which is exactly
why it should not be the human's job.

1. Establish the state — sign in as the right role, create or find the data,
   navigate, open the panel, apply the filter, scroll it into view.
2. Confirm the thing to be checked is actually on screen. Screenshot it.
3. Hand over precisely:

```
Ready: <one line — what to look at>

URL:      <exact, including query params>
Signed in as: <role / user>
State:    <what was created or chosen, and why this case shows it>
Look at:  <the specific element, where it is on screen>
Expected: <what it should do or show>
Contrast: <optional — the neighbouring case that should behave differently>
Not set up: <anything you could not stage, and why>
```

Leave the browser on that screen. Do not navigate away to do something else.

## Step 6a — Accumulate output

Write to `docs/plans/.scratch/review-<slug>.md`:

```markdown
# Review: <feature>
Date: <YYYY-MM-DD>
Branch: <branch>
Build verified: <sha> — <how freshness was checked>

## Summary
<one paragraph: what holds, what does not, what needs a decision>

## Items
### <section>
- **Verdict:** holds | defect | not reproduced | blocked | contested
- **Observed:** <what was seen, quoted>
- **Evidence:** <URL + state, and the probe used>
- **Action:** <one line, or the decision taken in Step 4>
```

Then:
> Review saved to `docs/plans/.scratch/review-<slug>.md`. Run `/ralph plan` next
> — it picks this up as the grill seed.

## Step 6b — Fix-now output

Per fix: make the edit, re-run lean validation, commit — then **re-verify in the
browser**. A fix that was not re-observed is not a fix. Close with a summary of
commits, one final end-to-end lean validation, and a suggestion of `/ralph pr`.

## Verdict discipline

The final report is a claim about the application, so it carries the same rules
as any other claim:

- Never report "verified" for something that was reasoned about rather than
  observed. If you did not open it, say you did not open it.
- Never let `blocked` quietly become `holds` because the section otherwise
  looked fine.
- If a diagnosis turns out wrong after it was written down, correct it plainly
  and say what the measurement showed. A wrong diagnosis that is discovered and
  corrected costs less than a confident one that survives.
- Report the count honestly, including what was not reached. "Nine of eleven
  sections verified, two blocked on seed data" beats "reviewed".

## Notes

- Never run E2E here — that is `/ralph e2e`. The browser walk and the E2E suite
  answer different questions, and an E2E run will break the preview (see Step 0).
- Never combine modes silently. If a fix is asked for during accumulate mode,
  ask whether to switch or just log it.
