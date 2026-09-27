// Injected before any page script (context.addInitScript). It measures and
// never changes behaviour: observers and a rAF probe only. Both sides of a
// before/after comparison get exactly the same probe, so its small cost
// cancels out.
//
// window.__m
//   .mark(name)                 a named point on the page clock
//   .metric(name, value)        a custom number (ms, count, px…) — app-specific
//   .window(t0?, t1?)           stats for a time range on performance.now()
//   .reset()                    start a fresh measuring window from now
//   .onWorkerMessage = fn       hook, only if window.__BA_CONFIG.wrapWorker
//
// Built-in signals (all on the main thread):
//   long tasks     PerformanceObserver "longtask" — main thread busy > 50 ms
//   frame gaps     requestAnimationFrame deltas — a gap > 50 ms is a visible stall
//   interactions   PerformanceObserver "event" — input → next paint (INP-like)
//   layout shifts  PerformanceObserver "layout-shift" (CLS without session windows)
(() => {
  if (window.__m) return;
  const cfg = window.__BA_CONFIG || {};
  const now = () => performance.now();
  const M = (window.__m = {
    t0: 0, long: [], gaps: [], events: [], shifts: [], marks: [], custom: [],
  });

  M.mark = (name) => { M.marks.push({ t: now(), name }); };
  M.metric = (name, value) => { M.custom.push({ t: now(), name, value: +value }); };
  M.reset = () => { M.t0 = now(); };

  // rAF probe: every frame the page actually produced, and the gap before it.
  let prev = 0;
  const raf = (t) => { if (prev) M.gaps.push({ t, d: t - prev }); prev = t; requestAnimationFrame(raf); };
  requestAnimationFrame(raf);
  // A hidden tab does not paint; a gap across it is not jank.
  document.addEventListener("visibilitychange", () => { prev = 0; });

  const observe = (type, fn, extra = {}) => {
    try { new PerformanceObserver((l) => l.getEntries().forEach(fn)).observe({ type, buffered: true, ...extra }); }
    catch { /* not supported in this engine — the stat stays empty, and says so */ }
  };
  observe("longtask", (e) => M.long.push({ t: e.startTime, d: e.duration }));
  observe("event", (e) => { if (e.interactionId) M.events.push({ t: e.startTime, d: e.duration, name: e.name }); }, { durationThreshold: 16 });
  observe("layout-shift", (e) => { if (!e.hadRecentInput) M.shifts.push({ t: e.startTime, v: e.value }); });

  // Opt-in: observe what workers post back, without touching the messages.
  // Off by default: replacing the constructor changes `Worker` identity.
  if (cfg.wrapWorker && window.Worker) {
    const W = window.Worker;
    const Wrapped = function (url, opts) {
      const w = new W(url, opts);
      w.addEventListener("message", (e) => { try { M.onWorkerMessage && M.onWorkerMessage(e.data, now()); } catch {} });
      return w;
    };
    Wrapped.prototype = W.prototype;
    window.Worker = Wrapped;
  }

  const pct = (arr, p) => { if (!arr.length) return 0; const s = [...arr].sort((a, b) => a - b); return s[Math.min(s.length - 1, Math.floor(s.length * p))]; };
  const r1 = (x) => Math.round(x * 10) / 10;

  M.window = (from = M.t0, to = now()) => {
    const inW = (e) => e.t >= from && e.t < to;
    const long = M.long.filter(inW), gaps = M.gaps.filter(inW).map((g) => g.d);
    const ev = M.events.filter(inW), sh = M.shifts.filter(inW);
    const custom = {};
    for (const c of M.custom.filter(inW)) {
      const s = (custom[c.name] ||= { n: 0, sum: 0, min: Infinity, max: -Infinity, last: 0, values: [] });
      s.n++; s.sum += c.value; s.min = Math.min(s.min, c.value); s.max = Math.max(s.max, c.value); s.last = c.value; s.values.push(c.value);
    }
    for (const s of Object.values(custom)) { s.median = pct(s.values, 0.5); delete s.values; }
    return {
      seconds: r1((to - from) / 1000),
      longTasks: long.length,
      longTaskMs: Math.round(long.reduce((a, e) => a + e.d, 0)),
      longTaskMax: Math.round(Math.max(0, ...long.map((e) => e.d))),
      frames: gaps.length,
      fps: r1(gaps.length / Math.max(0.001, (to - from) / 1000)),
      frameGapP95: r1(pct(gaps, 0.95)),
      frameGapMax: Math.round(Math.max(0, ...gaps)),
      stalls: gaps.filter((d) => d > 50).length,
      interactions: ev.length,
      interactionMax: Math.round(Math.max(0, ...ev.map((e) => e.d))),
      cls: Math.round(sh.reduce((a, e) => a + e.v, 0) * 1000) / 1000,
      custom,
    };
  };
})();
