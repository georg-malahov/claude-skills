// Example: shutter lag. Run with --camera <clip>.mjpeg from fake-camera.mjs.
// The page reads the burned-in frame number on screen at the press and in the
// photo it produced; the difference is the lag, measured in this very run.
const CLIP_FRAMES = 300; // fake-camera.mjs --seconds 10 at 30 fps

export const SCENARIO = {
  path: "/cam.html",
  async run(page, h) {
    // Wait until the fake camera plays and its frame code is readable.
    await page.waitForFunction(() => __frameCode.read(document.querySelector("video")) >= 0);
    // A probe of the scenario's own, identical on both sides: the frame on screen at the press.
    await page.evaluate(() => addEventListener("pointerdown", () => {
      window.__down = __frameCode.read(document.querySelector("video"));
    }, true));
    h.mark("ready");
    await h.caption("Pinch, then three shots of a shaky sheet");
    await h.pinch({ x: 195, y: 330 }, 80, 200);
    await h.hold(1000);
    for (let i = 1; i <= 3; i++) {
      await h.tap(page.locator("#shutter"));
      await page.waitForFunction((n) => window.shots === n, i);
      const r = await page.evaluate(async () => ({ down: window.__down, shot: await __frameCode.readBlob(window.lastPhoto) }));
      const lag = Math.round(((((r.shot - r.down) % CLIP_FRAMES) + CLIP_FRAMES) % CLIP_FRAMES) * 1000 / 30);
      await h.metric("shutterLagMs", lag);
      await h.caption(`On screen #${r.down} · in the photo #${r.shot} · ${lag} ms late`);
      await h.hold(2200);
    }
    h.mark("done");
    await h.caption("");
  },
};
