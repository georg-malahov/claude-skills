#!/usr/bin/env node
// Before → after numbers as a Markdown table, from the JSONs screenplay.mjs
// wrote. Pass any number of them: they are grouped by their `side`, and their
// runs pooled — so a --runs N file per side, or one file per interleaved run,
// both work. Each cell is the median with the min–max range, and a change only
// counts when the ranges do not overlap.
//
//   node table.mjs out/before.json out/after.json
//   node table.mjs runs/*/before.json runs/*/after.json
//     [--segments scroll,filter] [--metrics stalls,frameGapMax] [--higher-better fps,myScore]
//
// Custom metrics (h.metric / __m.metric) appear as "custom.<name>" and use the
// median of their values within the segment.
import { readFileSync } from "node:fs";
import { parseArgs } from "./lib.mjs";

const A = parseArgs();
const files = A._.map((f) => JSON.parse(readFileSync(f, "utf8")));
const pool = (side) => {
  const fs = files.filter((f) => f.side === side);
  if (!fs.length) return null;
  const key = (f) => JSON.stringify([f.throttle, f.preset, f.viewport, f.path, f.camera]);
  if (new Set(fs.map(key)).size > 1) console.log(`> ⚠️ The ${side} files were not all run under the same conditions.\n`);
  return { ...fs[0], runs: fs.flatMap((f) => f.runs) };
};
const before = pool("before"), after = pool("after");
if (!before || !after) { console.error("usage: node table.mjs BEFORE.json… AFTER.json… [--segments a,b] [--metrics m1,m2] [--higher-better m]  (sides are read from the files)"); process.exit(2); }

const NAMES = {
  longTasks: "long tasks", longTaskMs: "long-task time, ms", longTaskMax: "longest task, ms",
  frameGapMax: "worst frame gap, ms", frameGapP95: "frame gap p95, ms", stalls: "stalls (>50 ms frames)",
  fps: "frames per second", interactionMax: "slowest interaction, ms", cls: "layout shift (CLS)",
};
const DEFAULT = ["longTasks", "longTaskMs", "longTaskMax", "frameGapMax", "stalls", "interactionMax", "cls"];
const higher = new Set(["fps", ...String(A["higher-better"] ?? "").split(",").filter(Boolean)]);
const list = (v) => (v ? String(v).split(",").filter(Boolean) : null);

const segNames = list(A.segments) ?? [...new Set([
  ...before.runs.flatMap((r) => Object.keys(r.segments)),
  ...after.runs.flatMap((r) => Object.keys(r.segments)),
])];
if (!segNames.length) segNames.push("(whole run)");
const seg = (run, name) => (name === "(whole run)" ? run.summary : run.segments[name]);
const pick = (s, m) => {
  if (!s) return undefined;
  if (m.startsWith("custom.")) return s.custom?.[m.slice(7)]?.median;
  return s[m];
};
const med = (a) => { const s = [...a].sort((x, y) => x - y); const n = s.length; return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2; };
const fmt = (x) => (Math.abs(x) >= 100 || Number.isInteger(x) ? String(Math.round(x)) : x.toFixed(x < 1 ? 3 : 1));

const rows = [];
for (const name of segNames) {
  const customs = new Set();
  [...before.runs, ...after.runs].forEach((r) => Object.keys(seg(r, name)?.custom ?? {}).forEach((c) => customs.add(`custom.${c}`)));
  const metrics = list(A.metrics) ?? [...DEFAULT, ...customs];
  for (const m of metrics) {
    const b = before.runs.map((r) => pick(seg(r, name), m)).filter((x) => typeof x === "number");
    const a = after.runs.map((r) => pick(seg(r, name), m)).filter((x) => typeof x === "number");
    if (!b.length || !a.length) continue;
    const bm = med(b), am = med(a);
    const cell = (v, mm) => (v.length > 1 ? `${fmt(mm)} (${fmt(Math.min(...v))}–${fmt(Math.max(...v))})` : fmt(mm));
    const change = bm === 0 ? (am === 0 ? "0" : "new") : `${am > bm ? "+" : "−"}${Math.abs(Math.round(((am - bm) / bm) * 100))}%`;
    const good = higher.has(m) ? am > bm : am < bm;
    let verdict;
    if (am === bm) verdict = "same";
    else if (b.length > 1 && a.length > 1) {
      const overlap = Math.min(...a) <= Math.max(...b) && Math.min(...b) <= Math.max(...a);
      verdict = overlap ? "≈ no clear change (ranges overlap)" : good ? "better" : "**worse**";
    } else verdict = (good ? "better" : "**worse**") + " (1 run)";
    rows.push(`| ${name} | ${NAMES[m] ?? (m.startsWith("custom.") ? m.slice(7) : m)} | ${cell(b, bm)} | ${cell(a, am)} | ${change} | ${verdict} |`);
  }
}
const cond = [
  `${before.preset} ${before.viewport.width}×${before.viewport.height}`,
  before.throttle > 1 ? `CPU ×${before.throttle} (main thread only; workers unthrottled)` : "no CPU throttling",
  `runs: ${before.runs.length} before, ${after.runs.length} after`,
].join(" · ");
if (before.throttle !== after.throttle || before.preset !== after.preset || JSON.stringify(before.viewport) !== JSON.stringify(after.viewport) || before.path !== after.path || before.camera !== after.camera) {
  console.log("> ⚠️ The two sides were NOT run under the same conditions — fix that before using these numbers.\n");
}
console.log(`| segment | metric | before (${before.label}) | after (${after.label}) | change | |`);
console.log("|---|---|---|---|---|---|");
console.log(rows.join("\n"));
console.log(`\n_${cond}. Lower is better unless noted._`);
