// Before/after scenario — copy next to your work (e.g. <scratch>/ba/scenario.mjs)
// and edit. screenplay.mjs runs this SAME code against both builds:
//
//   node screenplay.mjs --scenario ba/scenario.mjs --side before --url $BEFORE_URL --out ba/out
//   node screenplay.mjs --scenario ba/scenario.mjs --side after  --url $AFTER_URL  --out ba/out
//
// Rules that keep the comparison honest:
//   - Never branch on the side. If the after build has a control the before
//     build lacks, reach it the same way on both (a URL, a shared selector) or
//     record two scenarios and say so in the captions.
//   - Seed data, sign in and warm caches in the same way on both sides.
//   - Every number on screen comes from h.measure / h.metric in THIS run.
//     Never type a number into a caption.
//   - Hold long enough after each step for a viewer to read the caption
//     (about 2.5 s for one line).
//
// h (the helper screenplay.mjs passes in):
//   h.caption(text)            caption bar on the video ("" hides it)
//   h.mark(name)               a named moment; compose.mjs --align <name> lines
//                              both videos up on it. Mark "ready" once the app is
//                              usable if load time is NOT what you compare.
//   h.hold(ms)                 wait (same on both sides)
//   h.tap(locator | {x, y})    tap on touch presets, click on desktop; a circle shows it
//   h.type(locator, text, ms)  tap, then type with a fixed delay per key
//   h.pinch({x, y}, from, to)  two-finger pinch, fingers `from`→`to` px apart (touch preset)
//   h.measure(name, fn)        run fn, return stats for exactly that window:
//                              { longTasks, longTaskMs, longTaskMax, frames, fps,
//                                frameGapP95, frameGapMax, stalls, interactions,
//                                interactionMax, cls, custom }
//                              and store them under `name` for table.mjs
//   h.metric(name, value)      record an app-specific number (median in the table)
//   h.stats()                  stats since the page loaded
//   h.page, h.cdp, h.preset    Playwright page, its CDP session, "mobile"|"desktop"

export const SCENARIO = {
  // Path appended to --url. Keep query strings and fixtures identical on both sides.
  path: "/",

  async run(page, h) {
    await page.waitForLoadState("networkidle");
    h.mark("ready");
    await h.caption("What we are about to do");
    await h.hold(1500);

    // The interaction the change is about, measured.
    const s = await h.measure("scroll", async () => {
      await page.mouse.wheel(0, 1200);
      await h.hold(1500);
    });
    await h.caption(`Scroll: ${s.stalls} stalls · worst frame ${s.frameGapMax} ms`);
    await h.hold(2500);

    // A tap with a visible circle:
    //   await h.tap(page.getByRole("button", { name: "Save" }));
    //
    // Typing at a fixed pace:
    //   const t = await h.measure("typing", () => h.type(page.locator("input[type=search]"), "mango", 120));
    //
    // Pinch (touch preset only):
    //   const box = await page.locator("canvas").boundingBox();
    //   await h.pinch({ x: box.x + box.width / 2, y: box.y + box.height / 2 }, 80, 220);
    //
    // Fake camera (run with --camera cam.mjpeg): which frame was on screen at
    // the press, and which one ended up in the photo:
    //   await page.evaluate(() => addEventListener("pointerdown", () => {
    //     window.__down = __frameCode.read(document.querySelector("video")); }, true));
    //   await h.tap(page.getByRole("button", { name: "Shutter" }));
    //   const { down, shot } = await page.evaluate(async () => ({ down: window.__down,
    //     shot: await __frameCode.readBlob(window.lastPhotoBlob) })); // however your app exposes the photo
    //   const lagMs = Math.round(((((shot - down) % CLIP_FRAMES) + CLIP_FRAMES) % CLIP_FRAMES) * 1000 / 30);
    //   await h.metric("shutterLagMs", lagMs);

    await h.caption("");
  },
};
