---
description: Live-browser visual sanity check — screenshot key routes at mobile + desktop viewports
argument-hint: 'optional comma-separated list of routes (e.g. /dashboard, /dashboard/kalender)'
---

# Preview Check — Visual Sanity Supplement to E2E

Open the running dev server in a real browser, navigate to a small set of routes, take mobile + desktop screenshots, and emit a markdown report. Manual supplement to E2E — meant to catch visual regressions that E2E assertions miss (layout breakage, overflow, broken images, raw `[object Object]` rendering, etc.).

**Not automated yet.** Use this a few times before wiring it into `/orchestrate` or `/create-pr`.

## Step 0: Pick the Routes

Parse `$ARGUMENTS`:
- If a comma-separated list of routes is provided, use it
- Otherwise, ask the user for the route list via plain chat. Suggest defaults based on what's changed:
  - From `git diff <default>...HEAD --name-only`, infer which routes are touched
  - Match against `src/app/**/page.tsx` (or framework equivalent) to derive route paths

Cap at 8 routes per run. More than that defeats the "sanity check" framing — split into multiple invocations.

## Step 1: Verify Dev Server

Check the dev server is reachable:

```bash
# Try the project's expected URL — usually http://localhost:3000
curl -sf http://localhost:3000 >/dev/null || echo "Dev server not reachable"
```

If not running, ask the user to start it (`bun run up`, `bun run dev`, or project equivalent) before proceeding. If multiple worktrees run in parallel, the URL may differ — confirm with the user.

## Step 2: Define Viewports

Default set (covers the common spread):

| Name | Viewport | UA hint |
|------|----------|---------|
| mobile | 390 × 844 | iPhone 12 |
| tablet | 768 × 1024 | iPad |
| desktop | 1440 × 900 | typical laptop |

The user can override with `viewports=mobile,desktop` etc. — parse `$ARGUMENTS` for an optional `viewports=` segment.

## Step 3: Screenshot Each Route × Viewport

Use the Claude Preview tools (`mcp__Claude_Preview__*`) or Chrome MCP (`mcp__Control_Chrome__*` / `mcp__Claude_in_Chrome__*`) depending on what's available. If neither is connected, fall back to a Playwright snippet (see Fallback below).

For each route, for each viewport:
1. Resize the browser to the viewport size
2. Navigate to the route
3. Wait for network idle / a sensible settle period (1–2s)
4. Take a screenshot
5. Save to `docs/previews/YYYY-MM-DD-HHMM/<route-slug>-<viewport>.png` (slugify route: `/dashboard/kalender` → `dashboard-kalender`)

If the route requires auth, ensure the browser session is authenticated first (use the project's "Ausfuellen" demo prefill button if available — see per-project memory).

## Step 4: Emit Markdown Report

Write `docs/previews/YYYY-MM-DD-HHMM/report.md`:

```markdown
# Preview Check — YYYY-MM-DD HH:MM

Branch: <current branch>
Commit: <short sha>
Dev server: <url>

## Routes × Viewports

### /dashboard
| mobile | tablet | desktop |
|--------|--------|---------|
| ![](dashboard-mobile.png) | ![](dashboard-tablet.png) | ![](dashboard-desktop.png) |

### /dashboard/kalender
| mobile | tablet | desktop |
|--------|--------|---------|
| ![](dashboard-kalender-mobile.png) | ... | ... |

## Notes
<any observed issues — overflows, missing content, etc.>
```

After writing the report:
- Output the file path to the user
- Inline the screenshots in chat if the harness supports it
- Ask if anything looks off; if so, recommend `/fix-to-green` to address

## Fallback: Playwright Snippet (no MCP browser available)

If no MCP browser tool is available, write a one-shot Playwright script and run it:

```ts
// scripts/preview-check.mjs (temporary)
import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

const ROUTES = process.argv[2].split(',');
const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'desktop', width: 1440, height: 900 },
];
const BASE = process.env.PREVIEW_BASE_URL ?? 'http://localhost:3000';
const OUT = `docs/previews/${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '')}`;
await mkdir(OUT, { recursive: true });
const browser = await chromium.launch();
for (const route of ROUTES) {
  for (const vp of VIEWPORTS) {
    const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
    const page = await ctx.newPage();
    await page.goto(BASE + route, { waitUntil: 'networkidle' });
    const slug = route.replace(/^\//, '').replace(/\//g, '-') || 'root';
    await page.screenshot({ path: path.join(OUT, `${slug}-${vp.name}.png`), fullPage: true });
    await ctx.close();
  }
}
await browser.close();
console.log(`Screenshots in ${OUT}`);
```

Run:
```bash
node scripts/preview-check.mjs "/dashboard,/dashboard/kalender"
# Or in container:
bun run dx node scripts/preview-check.mjs "/dashboard,/dashboard/kalender"
```

Delete the script after the run (it's temporary).

## Constraints

- This is a **manual** sanity check, not an automated gate
- Cap routes per invocation at 8 — split larger sets
- Always store screenshots under `docs/previews/<timestamp>/` so they're easy to find and gitignore-friendly
- Do not auto-attach screenshots to PRs yet — that comes later if this skill proves itself
- If the dev server isn't running, stop and ask the user to start it; don't try to start it yourself (avoids accidentally killing the user's existing session)
