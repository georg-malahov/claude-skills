#!/usr/bin/env python3
"""Assemble a voiced demo (project-agnostic): mux per-beat narration onto the
captured video, build the subtitle track + scene chapters, render the /video
player page.

  python3 build-demo.py <video.webm> <out_dir> <video_skill_scripts_dir> \
      [--timing PATH] [--narration-dir PATH] [--meta PATH] [--lang de]

Reads:
  --timing        cues: id, scene, caption, atMs, durationMs
                  (default test-results/preview/timing.json — written by the capture spec)
  --narration-dir beats: id, audioFile, durationMs   (default test-results/narration)
                  narration.json is optional — if absent or empty, a silent subtitled demo
                  is produced (no audio mux, no amix filter, -an transcode only).
  --meta          optional JSON {title, description} — the demo command writes this
                  from the plan + transcript; falls back to generic strings.

Seeding belongs in the capture spec's setup phase (beforeAll), NOT inline in the
recorded timeline — so this script does not special-case "preparing data" gaps.
A continuous cue runs from each beat to the next; long silent stretches mean the
screenplay/capture needs tightening, not a filler caption.

Bundled with the ralph plugin; a project may override it at
scripts/preview/build-demo.py (three-tier override chain).
"""
import argparse, json, os, subprocess

p = argparse.ArgumentParser()
p.add_argument("video_in")
p.add_argument("out_dir")
p.add_argument("sk_dir", help="video-skill scripts dir (for render_page.py + player.html)")
p.add_argument("--timing", default="test-results/preview/timing.json")
p.add_argument("--narration-dir", default="test-results/narration")
p.add_argument("--meta", default=None)
p.add_argument("--lang", default="de")
a = p.parse_args()

timing = json.load(open(a.timing))["cues"]
_narr_path = os.path.join(a.narration_dir, "narration.json")
if os.path.exists(_narr_path):
    narr = {b["id"]: b for b in json.load(open(_narr_path))["beats"]}
else:
    narr = {}
timing.sort(key=lambda c: c["atMs"])
os.makedirs(a.out_dir, exist_ok=True)

meta_in = json.load(open(a.meta)) if a.meta and os.path.exists(a.meta) else {}
LANG_LABEL = {"de": "Deutsch", "en": "English", "ru": "Русский"}.get(a.lang, a.lang)

dur = float(subprocess.check_output(
    ["ffprobe", "-v", "error", "-show_entries", "format=duration",
     "-of", "default=nw=1:nk=1", a.video_in]).decode().strip())
dur_ms = int(dur * 1000)


def fmt(ms):
    ms = int(max(0, ms)); s, ms = divmod(ms, 1000); m, s = divmod(s, 60); h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


# ── Mux: place each beat's mp3 at its atMs, mix (non-overlapping → full volume) ──
clips = [(c["id"], c["atMs"]) for c in timing
         if c["id"] in narr and os.path.exists(narr[c["id"]]["audioFile"])]

mp4 = os.path.join(a.out_dir, "video.mp4")
if clips:
    inputs = ["-i", a.video_in]
    filt, labels = [], []
    for i, (bid, at) in enumerate(clips, start=1):
        inputs += ["-i", narr[bid]["audioFile"]]
        filt.append(f"[{i}]adelay={at}|{at}[au{i}]")
        labels.append(f"[au{i}]")
    filt.append(f"{''.join(labels)}amix=inputs={len(clips)}:normalize=0:dropout_transition=0[aout]")
    subprocess.run(
        ["ffmpeg", "-y", *inputs,
         "-filter_complex", ";".join(filt),
         "-map", "0:v", "-map", "[aout]",
         "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", mp4],
        check=True, capture_output=True)
else:
    # Silent mode: no narration — transcode video only, no audio track.
    subprocess.run(
        ["ffmpeg", "-y", "-i", a.video_in,
         "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", "-an", mp4],
        check=True, capture_output=True)

# ── VTT: continuous cues (each runs until the next beat) ──
vtt = ["WEBVTT", ""]
for i, c in enumerate(timing):
    start = c["atMs"]
    nxt = timing[i + 1]["atMs"] if i + 1 < len(timing) else dur_ms
    if nxt <= start:
        nxt = start + 1500
    vtt += [f"{fmt(start)} --> {fmt(nxt)}", c["caption"], ""]
open(os.path.join(a.out_dir, "video.vtt"), "w").write("\n".join(vtt))

# ── Chapters: one per scene (at its first beat) ──
chapters, seen = [], set()
for c in timing:
    if c.get("scene") and c["scene"] not in seen:
        seen.add(c["scene"])
        chapters.append({"time": round(c["atMs"] / 1000, 1), "label": c["scene"]})

meta = {
    "title": meta_in.get("title", "Feature walkthrough (demo)"),
    "description": meta_in.get(
        "description",
        "Auto-generated narrated demo with subtitles and chapter navigation."),
    "chapters": chapters,
    "video_filename": "video.mp4",
    "subtitle_tracks": [{"src": "video.vtt", "srclang": a.lang, "label": LANG_LABEL, "default": True}],
}
open(os.path.join(a.out_dir, "metadata.json"), "w").write(json.dumps(meta, indent=2, ensure_ascii=False))

subprocess.run(
    ["python3", os.path.join(a.sk_dir, "render_page.py"),
     "--output-dir", a.out_dir, "--template", os.path.join(a.sk_dir, "player.html"),
     "--metadata", os.path.join(a.out_dir, "metadata.json"), "--download-button"],
    check=True)
print(f"BUILT {a.out_dir} | mp4 MB {round(os.path.getsize(mp4) / 1024 / 1024, 1)} | "
      f"clips {len(clips)} | chapters {len(chapters)} | cues {len(timing)} | video {dur:.1f}s")
