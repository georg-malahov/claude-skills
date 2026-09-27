#!/usr/bin/env node
// Fake camera for Chromium: any image becomes a looping .mjpeg clip, held in a
// hand (shake), slid across the view (slide) or still, with the frame number
// burned into a code bar on top so the page can tell WHICH frame it saw.
//
//   node fake-camera.mjs --image doc.jpg --out cam.mjpeg \
//     [--motion shake|slide|still] [--amp 1] [--seconds 10] [--size 720x960] \
//     [--bg "#6b4a2b"] [--no-code] [--preview preview.png]
//
// Use it with:
//   chromium.launch({ args: ["--use-fake-ui-for-media-stream",
//     "--use-fake-device-for-media-stream", "--use-file-for-fake-video-capture=/abs/cam.mjpeg"] })
// (screenplay.mjs does this for --camera FILE). Chromium plays an .mjpeg at
// 30 fps and loops it. WebKit and Firefox have no file-backed fake camera.
//
// Needs `sharp` (npm i sharp). The code bar layout is shared with frame-code.js.
import { writeFileSync } from "node:fs";
import { parseArgs, importFromProject } from "./lib.mjs";

const A = parseArgs();
if (!A.image || !A.out) {
  console.error("usage: node fake-camera.mjs --image IMG --out OUT.mjpeg [--motion shake|slide|still] [--amp 1] [--seconds 10] [--size 720x960] [--bg #6b4a2b] [--no-code] [--preview P.png]");
  process.exit(2);
}
const sharp = await importFromProject("sharp");
const FPS = 30; // Chromium's .mjpeg reader assumes 30 fps
const [W, H] = String(A.size ?? "720x960").split("x").map(Number);
const N = Math.round(FPS * +(A.seconds ?? 10));
const motion = A.motion ?? "shake", amp = +(A.amp ?? 1), bg = A.bg ?? "#6b4a2b", code = A.code !== false;
if (N > 1024 && code) throw new Error("the 10-bit frame code counts to 1023: keep --seconds <= 34");

// Leave room around the sheet so the motion never pushes it out of the frame.
const fit = motion === "slide" ? 0.62 : 0.78;
const doc = await sharp(A.image).rotate().resize(Math.round(W * fit), Math.round(H * fit), { fit: "inside" }).png().toBuffer();
const { width: dw, height: dh } = await sharp(doc).metadata();
const canvas = await sharp({ create: { width: W, height: H, channels: 3, background: bg } }).png().toBuffer();

const TAU = 2 * Math.PI;
function pose(t) {
  if (motion === "still") return { a: 0, s: 1, dx: 0, dy: 0 };
  if (motion === "slide") return { a: 0, s: 1, dx: Math.sin((TAU * t) / 2) * W * 0.17 * amp, dy: 0 };
  // Hand tremor: incommensurate sines, so the loop does not look like a metronome.
  return {
    a: amp * (2.0 * Math.sin(TAU * 1.3 * t) + 1.0 * Math.sin(TAU * 3.1 * t + 1)),
    s: 1 + amp * 0.03 * Math.sin(TAU * 0.9 * t + 0.5),
    dx: amp * W * (0.02 * Math.sin(TAU * 1.7 * t) + 0.01 * Math.sin(TAU * 4.3 * t)),
    dy: amp * H * (0.015 * Math.sin(TAU * 1.1 * t + 2) + 0.008 * Math.sin(TAU * 3.7 * t)),
  };
}

// 10-bit black/white code + the number in a red tag, in a white bar on top.
// Pixel units of a 720-wide frame, scaled to W — keep in step with frame-code.js.
function codeBar(f) {
  const k = W / 720;
  const bits = Array.from({ length: 10 }, (_, i) => (f >> (9 - i)) & 1);
  return Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${Math.ceil(72 * k)}">
    <g transform="scale(${k})">
      <rect width="720" height="72" fill="#fff"/>
      ${bits.map((b, i) => `<rect x="${20 + i * 48}" y="12" width="44" height="48" fill="${b ? "#000" : "#fff"}" stroke="#888"/>`).join("")}
      <rect x="510" y="12" width="190" height="48" fill="#c00"/>
      <text x="605" y="50" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-weight="bold" font-size="40" fill="#fff">#${String(f).padStart(3, "0")}</text>
    </g></svg>`);
}

const frames = [];
for (let f = 0; f < N; f++) {
  const { a, s, dx, dy } = pose(f / FPS);
  const sheet = await sharp(doc).resize(Math.round(dw * s)).rotate(a, { background: bg }).png().toBuffer();
  const m = await sharp(sheet).metadata();
  const left = Math.round((W - m.width) / 2 + dx), top = Math.round((H - m.height) / 2 + dy);
  const layers = [{ input: sheet, left: Math.max(0, left), top: Math.max(0, top) }];
  if (code) layers.push({ input: codeBar(f), left: 0, top: 0 });
  const jpg = await sharp(canvas).composite(layers).jpeg({ quality: 85, chromaSubsampling: "4:2:0" }).toBuffer();
  frames.push(jpg);
  if (A.preview && f === 0) writeFileSync(A.preview, jpg);
}
// An .mjpeg for Chromium is simply the JPEG frames back to back.
writeFileSync(A.out, Buffer.concat(frames));
console.log(`${A.out}: ${N} frames ${W}x${H} @${FPS} fps, motion=${motion}${code ? ", frame code 0.." + (N - 1) : ""}`);
