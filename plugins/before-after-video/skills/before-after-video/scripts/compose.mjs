#!/usr/bin/env node
// Compose recordings into one phone-friendly MP4 (H.264, yuv420p, faststart).
//
//   node compose.mjs --out ba.mp4 out/before.webm out/after.webm           # side by side
//   node compose.mjs --out ba.mp4 a/before.webm a/after.webm \
//                                 b/before.webm b/after.webm             # 2x2: rows = scenarios
//
// Options
//   --layout auto|hstack|vstack|grid   auto: 2 inputs → hstack, 4 → grid
//   --gap 8  --bg 111111               gutter between cells, its colour (hex, no #)
//   --align start|<mark>|none          line the inputs up on a mark from the sibling
//                                      <name>.json that screenplay.mjs wrote (default
//                                      start: the moment navigation began)
//   --lead 0.3                         seconds kept before the mark
//   --tail 1.5                         freeze the end this long; a shorter input
//                                      holds its last frame until the longest ends
//   --title "…" [--subtitle "…"]       a title card first (needs playwright); it
//   [--title-seconds 3]                lists the labels and the conditions (preset,
//   [--no-conditions]                  viewport, CPU throttling) from the JSONs
//   --max-width 1600  --crf 26         output size and quality
//   --frames 6                         also export N stills next to the mp4, to look at
//
// Nothing is sped up, slowed down or cut in the middle: each input is trimmed
// only at its start (to the same mark) and padded only at its end.
import { existsSync, readFileSync, mkdirSync, rmSync, statSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join, dirname, basename, resolve } from "node:path";
import { tmpdir } from "node:os";
import { parseArgs, importFromProject, probeDuration } from "./lib.mjs";

const A = parseArgs();
const inputs = A._.map((f) => resolve(f));
if (!A.out || inputs.length < 2 || inputs.length > 4) {
  console.error("usage: node compose.mjs --out OUT.mp4 [--layout auto|hstack|vstack|grid] [--align start] [--title …] IN1 IN2 [IN3 IN4]");
  process.exit(2);
}
for (const f of inputs) if (!existsSync(f)) throw new Error(`no such input: ${f}`);
const out = resolve(A.out);
const FPS = +(A.fps ?? 30), gap = +(A.gap ?? 8), bg = String(A.bg ?? "111111").replace(/^#/, "");
const lead = +(A.lead ?? 0.3), tail = +(A.tail ?? 1.5);
const align = A.align === false ? "none" : String(A.align ?? "start");
const layout = A.layout && A.layout !== "auto" ? A.layout : inputs.length > 2 ? "grid" : "hstack";
const run = (cmd, args) => {
  const r = spawnSync(cmd, args, { encoding: "utf8", maxBuffer: 64 << 20 });
  if (r.status !== 0) throw new Error(`${cmd} failed:\n${(r.stderr || "").split("\n").slice(-25).join("\n")}`);
  return r.stdout;
};

const meta = inputs.map((f) => {
  const j = f.replace(/\.[^.]+$/, ".json");
  return existsSync(j) ? JSON.parse(readFileSync(j, "utf8")) : null;
});
const size = (f) => run("ffprobe", ["-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", f]).trim().split(",").map(Number);
const cells = inputs.map((f, i) => {
  const [w, h] = size(f);
  const mark = align === "none" ? undefined : meta[i]?.runs?.[0]?.marks?.[align];
  if (align !== "none" && align !== "start" && mark === undefined) throw new Error(`${basename(f)}: no mark "${align}" in its JSON`);
  const trim = mark === undefined ? 0 : Math.max(0, mark - lead);
  return { f, w, h, trim, dur: probeDuration(f) - trim };
});
const W = Math.max(...cells.map((c) => c.w)), H = Math.max(...cells.map((c) => c.h));
const D = Math.max(...cells.map((c) => c.dur)) + tail;

const cols = layout === "grid" ? 2 : layout === "vstack" ? 1 : cells.length;
const rows = Math.ceil(cells.length / cols);
const SW = cols * W + (cols - 1) * gap, SH = rows * H + (rows - 1) * gap;
const scale = Math.min(1, +(A["max-width"] ?? 1600) / SW);
const even = (x) => Math.max(2, Math.round(x / 2) * 2);
const OW = even(SW * scale), OH = even(SH * scale);

// Title card, rendered by the browser so any script and font works.
let titlePng = null;
if (A.title) {
  const { chromium } = await importFromProject("playwright", "@playwright/test");
  const esc = (s) => String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]);
  const seen = new Map();
  meta.forEach((m) => m && !seen.has(m.label) && seen.set(m.label, m.side));
  const chips = [...seen].map(([l, s]) => `<span class="chip" style="background:${s === "before" ? "#b3261e" : s === "after" ? "#1b7f3b" : "#444"}">${esc(l)}</span>`).join("");
  // The conditions each recording was made under; rows that differ are listed apart.
  const conds = [...new Set(meta.filter(Boolean).map((m) => [
    `Chromium ${m.preset} ${m.viewport.width}×${m.viewport.height}`,
    m.throttle > 1 ? `CPU ×${m.throttle} (main thread only)` : "no CPU throttling",
    m.camera ? `fake camera: ${basename(m.camera)}` : "",
  ].filter(Boolean).join(" · ")))];
  const byRow = conds.length > 1;
  const cond = A.conditions === false ? "" : byRow
    ? meta.filter((m, i) => m && i % cols === 0).map((m, r) => `row ${r + 1} (${m.path}): ${[
      m.throttle > 1 ? `CPU ×${m.throttle} (main thread only)` : "no CPU throttling",
      m.camera ? `fake camera: ${basename(m.camera)}` : "",
    ].filter(Boolean).join(" · ")}`).join("\n")
    : conds[0] ?? "";
  const html = `<html><body style="margin:0;width:${OW}px;height:${OH}px;background:#${bg};color:#fff;display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif">
    <style>.chip{display:inline-block;margin:0 6px;padding:6px 14px;border-radius:999px;font-weight:600;font-size:${Math.round(OW / 40)}px}</style>
    <div style="text-align:center;padding:0 6%;max-width:88%">
      <div style="font-weight:700;font-size:${Math.round(OW / 17)}px;line-height:1.15">${esc(A.title)}</div>
      ${A.subtitle ? `<div style="margin-top:.8em;font-size:${Math.round(OW / 32)}px;opacity:.85;line-height:1.35">${esc(A.subtitle).replace(/\\n|\n/g, "<br>")}</div>` : ""}
      ${chips ? `<div style="margin-top:1.4em">${chips}</div>` : ""}
      ${cond ? `<div style="margin-top:1.2em;font-size:${Math.round(OW / 48)}px;opacity:.6;line-height:1.4">${esc(cond).replace(/\n/g, "<br>")}</div>` : ""}
    </div></body></html>`;
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: OW, height: OH } });
  await p.setContent(html);
  titlePng = join(tmpdir(), `ba-title-${process.pid}.png`);
  await p.screenshot({ path: titlePng });
  await b.close();
}

const args = ["-y", "-v", "error"];
cells.forEach((c) => args.push("-i", c.f));
if (titlePng) args.push("-loop", "1", "-framerate", String(FPS), "-t", String(+(A["title-seconds"] ?? 3)), "-i", titlePng);

const f = [];
cells.forEach((c, i) => {
  f.push(`[${i}:v]trim=start=${c.trim.toFixed(3)},setpts=PTS-STARTPTS,fps=${FPS},`
    + `scale=${W}:${H}:force_original_aspect_ratio=decrease,pad=${W}:${H}:(ow-iw)/2:(oh-ih)/2:color=0x${bg},setsar=1,`
    + `tpad=stop_mode=clone:stop_duration=${(D - c.dur).toFixed(3)},trim=duration=${D.toFixed(3)}[c${i}]`);
});
const pos = cells.map((_, i) => `${(i % cols) * (W + gap)}_${Math.floor(i / cols) * (H + gap)}`).join("|");
f.push(`${cells.map((_, i) => `[c${i}]`).join("")}xstack=inputs=${cells.length}:layout=${pos}:fill=0x${bg},scale=${OW}:${OH},setsar=1,format=yuv420p[stack]`);
if (titlePng) {
  f.push(`[${cells.length}:v]scale=${OW}:${OH},setsar=1,fps=${FPS},format=yuv420p[title]`);
  f.push(`[title][stack]concat=n=2:v=1:a=0[vout]`);
}
args.push("-filter_complex", f.join(";"), "-map", titlePng ? "[vout]" : "[stack]",
  "-c:v", "libx264", "-preset", "slow", "-crf", String(A.crf ?? 26), "-pix_fmt", "yuv420p",
  "-profile:v", "high", "-movflags", "+faststart", "-an", out);
run("ffmpeg", args);
if (titlePng) rmSync(titlePng, { force: true });

const mb = statSync(out).size / 1e6;
const total = D + (titlePng ? +(A["title-seconds"] ?? 3) : 0);
console.log(`${out}: ${OW}x${OH}, ${total.toFixed(1)} s, ${mb.toFixed(1)} MB`);
cells.forEach((c) => console.log(`  ${basename(dirname(c.f))}/${basename(c.f)}: from ${c.trim.toFixed(2)} s, ${c.dur.toFixed(1)} s`));
if (mb > 10) console.warn("  over 10 MB: GitHub's free plan refuses larger videos in comments — raise --crf or lower --max-width");

if (A.frames) {
  const n = +A.frames, dir = out.replace(/\.[^.]+$/, "") + "-frames";
  rmSync(dir, { recursive: true, force: true }); mkdirSync(dir, { recursive: true });
  for (let k = 0; k < n; k++) {
    const t = ((k + 0.5) * total) / n;
    run("ffmpeg", ["-y", "-v", "error", "-ss", t.toFixed(2), "-i", out, "-frames:v", "1", join(dir, `${String(k).padStart(2, "0")}-${t.toFixed(1)}s.png`)]);
  }
  console.log(`  stills: ${dir}/`);
}
