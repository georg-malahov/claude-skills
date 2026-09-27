#!/usr/bin/env node
// Before/after screenplay harness: runs ONE scenario against one side at a
// time. Run it twice — against the `before` server (main) and the `after`
// server (the branch) — then compose.mjs puts the recordings side by side.
//
//   node screenplay.mjs --scenario ba/scenario.mjs --side before --url http://localhost:4101 --out ba/out
//   node screenplay.mjs --scenario ba/scenario.mjs --side after  --url http://localhost:4102 --out ba/out
//
// The scenario is a small module (start from scenario.template.mjs) exporting
// SCENARIO = { path, async run(page, h) }. It must not branch on the side:
// the same code runs on both, or the comparison proves nothing. Run from the
// project root so the project's own playwright is used.
//
// Options
//   --preset mobile|desktop   390x844 touch phone (default) | 1280x800 desktop
//   --viewport WxH            override the preset's size
//   --throttle N              CPU slowdown via CDP — the page's main thread ONLY:
//                             Chromium refuses it for workers ("Operation is only
//                             supported for pages, not workers"), so work moved
//                             into a worker runs at full speed on both sides
//   --camera FILE.mjpeg       Chromium fake camera fed from a file (fake-camera.mjs);
//                             also injects frame-code.js (window.__frameCode)
//   --label TEXT              badge text; default "BEFORE · main" / "AFTER · this branch"
//   --lang ru                 Russian default labels ("ДО — main" / "ПОСЛЕ — эта ветка")
//   --hud                     live corner readout of long tasks / worst frame
//   --caption-pos top|bottom|<px from top>   where captions sit (default bottom)
//   --badge-pos top|top-left|top-right|bottom   (default top)
//   --runs N --no-video       measure N runs without recording (for the numbers table)
//   --wrap-worker             let instrument.js observe worker messages (__m.onWorkerMessage)
//   --locale, --timezone, --color-scheme   fixed per run (defaults en-US, UTC, light)
//   --headed                  show the browser
//
// Writes <out>/<side>.webm (unless --no-video) and <out>/<side>.json:
// { side, label, url, path, preset, viewport, throttle, camera, runs: [{
//   summary, segments, marks, captions, errors }] }. Marks and captions are
// seconds from the start of the recording; compose.mjs --align <mark> uses them.
import { writeFileSync, mkdirSync, renameSync, rmSync, existsSync } from "node:fs";
import { resolve, join, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs, importFromProject } from "./lib.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const A = parseArgs();
if (!A.scenario || !A.side || !A.url) {
  console.error("usage: node screenplay.mjs --scenario FILE.mjs --side before|after --url URL [--out DIR] [--preset mobile|desktop] [--throttle N] [--camera FILE] …");
  process.exit(2);
}
const { SCENARIO } = await import(pathToFileURL(resolve(String(A.scenario))).href);
if (!SCENARIO || typeof SCENARIO.run !== "function") throw new Error(`${A.scenario} must export SCENARIO = { path, async run(page, h) }`);
const side = String(A.side);
const outDir = resolve(A.out ?? "out");
const video = A.video !== false;
const runs = +(A.runs ?? 1);
if (video && runs > 1) { console.error("record one run; measure repeated runs with --runs N --no-video"); process.exit(2); }
mkdirSync(outDir, { recursive: true });

const LABELS = {
  en: { before: "BEFORE · main", after: "AFTER · this branch" },
  ru: { before: "ДО — main", after: "ПОСЛЕ — эта ветка" },
};
const label = A.label ?? (LABELS[A.lang] ?? LABELS.en)[side] ?? side;
const color = side === "before" ? "#b3261e" : side === "after" ? "#1b7f3b" : "#3b3b3b";

const PRESETS = {
  mobile: {
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36",
  },
  desktop: { viewport: { width: 1280, height: 800 }, deviceScaleFactor: 1, isMobile: false, hasTouch: false },
};
const presetName = A.preset ?? "mobile";
const preset = structuredClone(PRESETS[presetName] ?? PRESETS.mobile);
if (A.viewport) { const [w, h] = String(A.viewport).split("x").map(Number); preset.viewport = { width: w, height: h }; }

const { chromium } = await importFromProject("playwright", "@playwright/test");
const launchArgs = [];
if (A.camera) {
  if (!existsSync(A.camera)) throw new Error(`no such camera file: ${A.camera}`);
  launchArgs.push("--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
    `--use-file-for-fake-video-capture=${resolve(A.camera)}`);
}

// The overlay: side badge, caption bar, a fading circle on every press, a
// faint trail while a finger or button is down, optional HUD. It lives in a
// shadow root under <html>, so the app's own DOM and styles are untouched, and
// it re-attaches itself if a framework replaces the document's children.
function overlay({ label, color, captionPos, badgePos, hud }) {
  if (window.top !== window) return;
  let host, root;
  const css = `
    .badge{position:fixed;${{ top: "top:12px;left:50%;transform:translateX(-50%)", "top-left": "top:12px;left:12px", "top-right": "top:12px;right:12px", bottom: "bottom:12px;left:50%;transform:translateX(-50%)" }[badgePos] || "top:12px;left:50%;transform:translateX(-50%)"};
      font:600 13px/1.2 system-ui,sans-serif;color:#fff;background:${color};padding:5px 12px;border-radius:999px;box-shadow:0 2px 8px rgba(0,0,0,.3);white-space:nowrap}
    .cap{position:fixed;left:10px;right:10px;${captionPos === "top" ? "top:52px" : /^\d+$/.test(captionPos) ? `top:${captionPos}px` : "bottom:22px"};
      font:600 15px/1.35 system-ui,sans-serif;color:#fff;background:rgba(0,0,0,.76);padding:8px 12px;border-radius:12px;text-align:center;display:none}
    .dot{position:fixed;width:44px;height:44px;margin:-22px 0 0 -22px;border-radius:50%;background:rgba(255,255,255,.55);border:2px solid rgba(0,0,0,.4);
      animation:ba-dot .6s ease-out forwards}
    .trail{position:fixed;width:18px;height:18px;margin:-9px 0 0 -9px;border-radius:50%;background:rgba(255,255,255,.6);border:2px solid rgba(0,0,0,.45);
      animation:ba-trail .5s ease-out forwards}
    @keyframes ba-dot{from{transform:scale(1);opacity:1}to{transform:scale(1.6);opacity:0}}
    @keyframes ba-trail{from{opacity:1}to{opacity:0}}
    .hud{position:fixed;left:8px;${badgePos === "bottom" ? "top:8px" : "top:44px"};font:600 11px/1.3 ui-monospace,Menlo,monospace;color:#fff;background:rgba(0,0,0,.6);padding:4px 7px;border-radius:6px;white-space:pre}`;
  const ensure = () => {
    if (host && host.isConnected) return root;
    if (!document.documentElement) return null;
    host = document.createElement("ba-overlay");
    host.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483647";
    root = host.attachShadow({ mode: "closed" });
    root.innerHTML = `<style>${css}</style><div class="badge"></div><div class="cap"></div>${hud ? '<div class="hud"></div>' : ""}`;
    root.querySelector(".badge").textContent = label;
    const c = root.querySelector(".cap");
    if (window.__baCaption) { c.textContent = window.__baCaption; c.style.display = "block"; }
    document.documentElement.appendChild(host);
    return root;
  };
  setInterval(ensure, 400);
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", ensure); else ensure();

  window.__caption = (t) => {
    window.__baCaption = t;
    const r = ensure(); if (!r) return;
    const c = r.querySelector(".cap"); c.textContent = t; c.style.display = t ? "block" : "none";
  };
  // CSS animations, not transitions: a transition set in the same frame as
  // the element appears may never run, and the mark is never seen.
  const spot = (cls, x, y) => {
    const r = ensure(); if (!r) return;
    const d = document.createElement("div"); d.className = cls; d.style.left = x + "px"; d.style.top = y + "px";
    r.appendChild(d);
    setTimeout(() => d.remove(), 700);
  };
  window.__baDot = (x, y) => spot("dot", x, y);
  window.__baTrail = (x, y) => spot("trail", x, y);
  addEventListener("pointerdown", (e) => spot("dot", e.clientX, e.clientY), true);
  let last = 0;
  addEventListener("pointermove", (e) => {
    if (!e.buttons && !(e.pointerType === "touch" && e.pressure > 0)) return;
    const t = performance.now(); if (t - last < 35) return; last = t;
    spot("trail", e.clientX, e.clientY);
  }, true);
  if (hud) setInterval(() => {
    const r = ensure(); const el = r && r.querySelector(".hud"); if (!el || !window.__m) return;
    const s = window.__m.window(0);
    el.textContent = `long tasks ${s.longTasks} · ${s.longTaskMs} ms\nworst frame ${s.frameGapMax} ms · stalls ${s.stalls}`;
  }, 250);
}

async function runOnce(k) {
  const browser = await chromium.launch({ args: launchArgs, headless: !A.headed });
  const ctx = await browser.newContext({
    ...preset,
    locale: A.locale ?? "en-US",
    timezoneId: A.timezone ?? "UTC",
    colorScheme: A["color-scheme"] ?? "light",
    ...(video ? { recordVideo: { dir: join(outDir, `.raw-${side}`), size: preset.viewport } } : {}),
  });
  await ctx.addInitScript({ content: `window.__BA_CONFIG = ${JSON.stringify({ wrapWorker: !!A["wrap-worker"] })};` });
  await ctx.addInitScript({ path: join(HERE, "instrument.js") });
  if (A.camera) await ctx.addInitScript({ path: join(HERE, "frame-code.js") });
  await ctx.addInitScript(overlay, {
    label, color, captionPos: String(A["caption-pos"] ?? "bottom"), badgePos: String(A["badge-pos"] ?? "top"), hud: !!A.hud,
  });

  const page = await ctx.newPage();
  const tVideo0 = Date.now(); // the recording starts with the page
  const since = () => Math.round(Date.now() - tVideo0) / 1000;
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 300)));

  const cdp = await ctx.newCDPSession(page);
  // CPU throttling applies to this page's main thread. A navigation can move
  // the page to another renderer process and drop it, so it is applied again
  // on every main-frame navigation.
  const throttle = +(A.throttle ?? 1);
  const applyThrottle = () => throttle > 1 && cdp.send("Emulation.setCPUThrottlingRate", { rate: throttle }).catch(() => {});
  await applyThrottle();
  page.on("framenavigated", (f) => { if (f === page.mainFrame()) applyThrottle(); });

  const marks = {}, captions = [], segments = {};
  const h = {
    page, cdp, preset: presetName,
    mark(name) { marks[name] = since(); page.evaluate((n) => window.__m && window.__m.mark(n), name).catch(() => {}); },
    async caption(text) { captions.push({ t: since(), text }); await page.evaluate((t) => window.__caption && window.__caption(t), text).catch(() => {}); },
    hold: (ms) => page.waitForTimeout(ms),
    async tap(target) {
      if (target && typeof target.x === "number" && !target.click) {
        return preset.hasTouch ? page.touchscreen.tap(target.x, target.y) : page.mouse.click(target.x, target.y);
      }
      return preset.hasTouch ? target.tap() : target.click();
    },
    async type(locator, text, perKeyMs = 90) { await h.tap(locator); await locator.pressSequentially(text, { delay: perKeyMs }); },
    // Two-finger pinch around c: the fingers move from `from` to `to` px apart.
    async pinch(c, from, to, { steps = 24, stepMs = 25 } = {}) {
      if (!preset.hasTouch) throw new Error("pinch needs a touch preset (--preset mobile)");
      const pts = (g) => [{ x: c.x - g / 2, y: c.y, id: 1 }, { x: c.x + g / 2, y: c.y, id: 2 }];
      await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: pts(from) });
      for (let i = 1; i <= steps; i++) {
        const p = pts(from + ((to - from) * i) / steps);
        await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: p });
        // CDP touches do not reliably reach pointermove listeners: draw the fingers here.
        await page.evaluate((p) => p.forEach(({ x, y }) => window.__baTrail && window.__baTrail(x, y)), p).catch(() => {});
        await page.waitForTimeout(stepMs);
      }
      await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    },
    async measure(name, fn) {
      const from = await page.evaluate(() => performance.now());
      await fn();
      const to = await page.evaluate(() => performance.now());
      await page.waitForTimeout(150); // observers deliver entries asynchronously
      const s = await page.evaluate(([a, b]) => window.__m.window(a, b), [from, to]);
      segments[name] = s;
      return s;
    },
    stats: () => page.evaluate(() => window.__m.window(0)),
    metric: (name, value) => page.evaluate(([n, v]) => window.__m.metric(n, v), [name, value]),
  };

  let failure = null;
  try {
    h.mark("start");
    await page.goto(new URL(SCENARIO.path ?? "/", A.url).href);
    await SCENARIO.run(page, h);
    h.mark("end");
  } catch (e) {
    failure = e;
  }
  const summary = await h.stats().catch(() => null);

  await ctx.close();
  let file = null;
  if (video) {
    // A failed run keeps its recording under another name: watch it to see where it stuck.
    file = join(outDir, failure ? `${side}.failed.webm` : `${side}.webm`);
    renameSync(await page.video().path(), file);
    rmSync(join(outDir, `.raw-${side}`), { recursive: true, force: true });
  }
  await browser.close();
  if (failure) {
    console.error(`[${side}] the scenario failed${file ? ` (recording: ${file})` : ""}:\n${failure.message.split("\n").slice(0, 6).join("\n")}`);
    process.exit(1);
  }
  if (errors.length) console.warn(`[${side}] run ${k + 1}: ${errors.length} page error(s) — ${errors[0]}`);
  return { file, run: { summary, segments, marks, captions, errors } };
}

const results = [];
for (let k = 0; k < runs; k++) results.push(await runOnce(k));
const report = {
  side, label, url: A.url, path: SCENARIO.path ?? "/", preset: presetName, viewport: preset.viewport,
  throttle: +(A.throttle ?? 1),
  camera: A.camera ? resolve(A.camera) : null,
  video: results[0].file,
  runs: results.map((r) => r.run),
};
writeFileSync(join(outDir, `${side}.json`), JSON.stringify(report, null, 2));
console.log(`${side}: ${runs} run(s)${video ? " → " + results[0].file : ""}, ${join(outDir, side + ".json")}`);
for (const [name, s] of Object.entries(results[0].run.segments)) {
  console.log(`  ${name}: long tasks ${s.longTasks} (${s.longTaskMs} ms, max ${s.longTaskMax}) · worst frame ${s.frameGapMax} ms · stalls ${s.stalls}`);
}
