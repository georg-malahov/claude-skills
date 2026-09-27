// Reads the frame number that fake-camera.mjs burns into every frame, from
// anything the page can draw: the live <video>, an ImageBitmap, a canvas, an
// <img>, or (async) a Blob such as the photo the app just produced.
//
// Inject with context.addInitScript({ path: "frame-code.js" }), then in the page:
//   __frameCode.read(videoEl)            -> 0..1023, or -1 if no code is visible
//   await __frameCode.readBlob(blob)     -> same, for a File/Blob
//
// Shutter lag = (frame in the photo) - (frame on screen at pointerdown), in
// frames of 1000/30 ms, modulo the clip length (the clip loops).
//
// The layout below is shared with fake-camera.mjs — change both or neither.
// Units are pixels of a 720-wide frame and scale with the actual width.
(() => {
  const REF_W = 720, BITS = 10, BIT_X0 = 20, BIT_STEP = 48, BIT_W = 44, BAR_MID_Y = 36;
  const PAPER_X = 8, TAG_X = 520; // white bar background, red number tag (left of its digits)
  const size = (s) => [s.videoWidth || s.naturalWidth || s.displayWidth || s.width, s.videoHeight || s.naturalHeight || s.displayHeight || s.height];

  function read(src) {
    const [w, h] = size(src);
    if (!w || !h) return -1;
    const cw = 360, ch = Math.max(1, Math.round((cw * h) / w)), k = cw / REF_W;
    const c = document.createElement("canvas"); c.width = cw; c.height = ch;
    const g = c.getContext("2d", { willReadFrequently: true });
    g.drawImage(src, 0, 0, cw, ch);
    const px = (x) => g.getImageData(Math.round(x * k), Math.round(BAR_MID_Y * k), 1, 1).data;
    // Sanity: a white bar and a red tag where the generator put them. A cropped
    // or letterboxed source fails here instead of returning a wrong number.
    const paper = px(PAPER_X), tag = px(TAG_X);
    if (paper[0] + paper[1] + paper[2] < 600 || !(tag[0] > 150 && tag[1] < 90 && tag[2] < 90)) return -1;
    let n = 0;
    for (let i = 0; i < BITS; i++) {
      const d = px(BIT_X0 + i * BIT_STEP + BIT_W / 2);
      n = n * 2 + (d[0] + d[1] + d[2] < 384 ? 1 : 0);
    }
    return n;
  }

  async function readBlob(blob) {
    const bm = await createImageBitmap(blob);
    try { return read(bm); } finally { bm.close && bm.close(); }
  }

  window.__frameCode = { read, readBlob, fps: 30 };
})();
