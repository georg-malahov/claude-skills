// Example: typing into a filter whose ranking blocks the main thread (before)
// or runs in a worker (after). Run with --throttle 4 so the stall is visible.
export const SCENARIO = {
  path: "/index.html",
  async run(page, h) {
    await page.waitForLoadState("load");
    h.mark("ready");
    await h.caption("Typing “mango 1” into the filter");
    await h.hold(800);
    const s = await h.measure("typing", () => h.type(page.locator("#q"), "mango 1", 120));
    await h.hold(600);
    await h.caption(`Main thread blocked ${s.longTaskMs} ms · worst frame ${s.frameGapMax} ms`);
    await h.hold(2500);
  },
};
