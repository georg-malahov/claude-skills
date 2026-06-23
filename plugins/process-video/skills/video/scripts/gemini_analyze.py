#!/usr/bin/env python3
"""Gemini analysis/transcription engine for the video skill (via OpenRouter).

Two modes — picked by the user's `analysis_mode` preference:

  audio  — extract a compact mp3, send it INLINE to a Gemini flash-lite model,
           get a verbatim [MM:SS] transcript, and write video.srt / video.vtt.
           A cheaper drop-in for Deepgram when exact word-level timing is not
           critical. No S3 upload needed.

  video  — encode a <=15 MiB, fps=1 proxy, upload it to S3 (Gemini fetches the
           URL, capped at 15 MiB), send ONE combined request for a developer
           analysis + verbatim transcript, then extract screenshot frames at the
           finding timestamps into the output dir. This is the rich path that
           reads the SCREEN, not just the audio.

Credentials are read from --credential-dir (never CLI args):
  openrouter_token   single-line OpenRouter key
  s3_credentials     endpoint/bucket/access_key/secret_key (video mode only)

Output contract for the model:
  - writes video.srt + video.vtt into --output-dir (both modes)
  - video mode also writes shot-<sec>.jpg frames + prints RESULT_JSON: <json>
    with {analysis, screenshots, transcript_file, cost, proxy_url}
  - prints [PROGRESS] lines and a final [COST] line
"""
import argparse, base64, json, os, subprocess, sys, urllib.request

from s3_util import load_s3_credentials, cp as s3_cp, rm as s3_rm
from subtitle_util import markers_to_cues, write_subtitles

DEFAULT_MODEL = "google/gemini-3.1-flash-lite"
MAX_FETCH_BYTES = 15 * 1024 * 1024  # Gemini URL-fetch cap


# ---------- credentials ----------
def load_token(cred_dir):
    p = os.path.join(cred_dir, "openrouter_token")
    if os.environ.get("OPENROUTER_TOKEN"):
        return os.environ["OPENROUTER_TOKEN"].strip()
    if not os.path.isfile(p):
        sys.exit(f"Error: OpenRouter token not found at {p}")
    return open(p).read().strip()


# ---------- openrouter ----------
def call_openrouter(token, messages, model, response_json=False):
    payload = {"model": model, "messages": messages, "usage": {"include": True}}
    if response_json:
        payload["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": "application/json",
                 "X-Title": "video-skill gemini_analyze"},
        method="POST")
    with urllib.request.urlopen(req, timeout=1800) as r:
        return json.load(r)


# ---------- ffmpeg helpers ----------
def probe_duration(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration", "-of",
                          "default=noprint_wrappers=1:nokey=1", video],
                         capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def extract_mp3(video, out_path):
    subprocess.run(["ffmpeg", "-y", "-i", video, "-vn", "-ac", "1",
                    "-c:a", "libmp3lame", "-b:a", "48k", out_path,
                    "-loglevel", "error"], check=True)


def encode_proxy(video, out_path):
    """fps=1, native-ish res proxy, escalating compression until <=15 MiB."""
    attempts = [("1920", 26), ("1920", 32), ("1280", 32), ("960", 34)]
    for scale, crf in attempts:
        subprocess.run(["ffmpeg", "-y", "-i", video,
                        "-vf", f"scale={scale}:-2,fps=1",
                        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
                        "-c:a", "aac", "-b:a", "48k", "-ac", "1",
                        "-movflags", "+faststart", out_path,
                        "-loglevel", "error"], check=True)
        size = os.path.getsize(out_path)
        print(f"[PROGRESS] proxy {scale}px crf{crf}: {size/1048576:.1f} MiB", flush=True)
        if size <= MAX_FETCH_BYTES:
            return size
    return os.path.getsize(out_path)


def extract_frame(video, sec, out_path, width=1280):
    subprocess.run(["ffmpeg", "-y", "-ss", str(sec), "-i", video,
                    "-frames:v", "1", "-vf", f"scale={width}:-2",
                    "-q:v", "3", out_path, "-loglevel", "error"], check=True)


def write_transcript_subtitles(text, out_dir, video_end):
    """Parse [MM:SS]-marker transcript → video.srt/.vtt. Returns cue count."""
    return write_subtitles(out_dir, markers_to_cues(text, video_end))


def extract_first_json(s):
    """Return the first balanced {...} object in s (ignores trailing prose /
    fences / a second object), respecting strings and escapes. None if absent."""
    start = s.find("{")
    if start < 0:
        return None
    depth, instr, esc = 0, False, False
    for i in range(start, len(s)):
        c = s[i]
        if instr:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                instr = False
        elif c == '"':
            instr = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return None


def report_cost(data, label):
    u = data.get("usage", {}) or {}
    cost = u.get("cost")
    print(f"[COST] {label}: ${cost:.5f} "
          f"(prompt {u.get('prompt_tokens')}, completion {u.get('completion_tokens')})"
          if cost is not None else f"[COST] {label}: unknown", flush=True)
    return u


# ---------- prompts ----------
TRANSCRIPT_PROMPT = (
    "Transkribiere den gesprochenen Kommentar WÖRTLICH. Setze alle 1-2 Sätze "
    "einen Zeitstempel [MM:SS]. Exakter Wortlaut (keine Zusammenfassung), inkl. "
    "Fachbegriffe/UI-Bezeichnungen. Nur das Transkript. Sprache: wie im Audio."
)

VIDEO_PROMPT = """Du analysierst ein Screencast-Video. Nutze ausdrücklich die VISUELLEN Informationen am Bildschirm (Buttons, Menüs, Labels, angezeigte Texte, Mauszeiger), nicht nur die Tonspur.

Gib AUSSCHLIESSLICH ein JSON-Objekt zurück (keine Markdown-Fences) mit genau diesen Schlüsseln:
{
  "title": "kurzer Titel",
  "description": "1-3 Sätze",
  "summary": "3-5 Sätze",
  "language": "de|en|ru (Sprache des Kommentars)",
  "chapters": [{"time": <sek>, "label": "..."}],
  "findings": [{"type": "bug|ux|idea", "title": "...", "severity": "hoch|mittel|niedrig|kritisch", "time": <sek>, "ui": "sichtbares UI-Element/Label", "verbatim": "wörtliches Zitat des Sprechers an dieser Stelle"}],
  "visual_details": [{"time": <sek>, "note": "Detail, das NUR im Bild sichtbar ist (exakte Beschriftung/Zustand)"}],
  "questions": ["offene Frage", ...],
  "tasks": [{"priority": "kritisch|hoch|mittel|niedrig", "text": "konkreter Schritt"}],
  "transcript": "wörtliches Transkript mit [MM:SS]-Markern alle 1-2 Sätze"
}
Sei konkret. `time` immer in GANZEN SEKUNDEN. Liefere mind. 5 visual_details als Beleg, dass die Videoanalyse mehr erfasst als reines Audio."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--mode", required=True, choices=["audio", "video"])
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--credential-dir", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--key", help="S3 share key (video mode: where the proxy lives)")
    ap.add_argument("--s3-prefix", default="sharing-videos")
    ap.add_argument("--reuse-proxy-url", help="skip encode/upload, use this URL (testing)")
    ap.add_argument("--keep-proxy", action="store_true",
                    help="video mode: keep the proxy on S3 instead of deleting it")
    args = ap.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    token = load_token(args.credential_dir)
    dur = probe_duration(args.video)

    if args.mode == "audio":
        mp3 = os.path.join(args.output_dir, "_audio.mp3")
        print("[PROGRESS] extracting audio…", flush=True)
        extract_mp3(args.video, mp3)
        b64 = base64.b64encode(open(mp3, "rb").read()).decode()
        os.remove(mp3)
        messages = [{"role": "user", "content": [
            {"type": "text", "text": TRANSCRIPT_PROMPT},
            {"type": "input_audio", "input_audio": {"data": b64, "format": "mp3"}},
        ]}]
        print("[PROGRESS] transcribing via Gemini…", flush=True)
        data = call_openrouter(token, messages, args.model)
        txt = data["choices"][0]["message"]["content"]
        n = write_transcript_subtitles(txt, args.output_dir, dur)
        report_cost(data, "audio-transcript")
        print(f"[PROGRESS] wrote {n} subtitle cues → video.srt / video.vtt", flush=True)
        return

    # ---- video mode ----
    creds = load_s3_credentials(args.credential_dir)
    proxy_key = None
    if args.reuse_proxy_url:
        proxy_url = args.reuse_proxy_url
    else:
        if not args.key:
            sys.exit("Error: --key required in video mode (proxy upload location)")
        proxy = os.path.join(args.output_dir, "_proxy.mp4")
        print("[PROGRESS] encoding proxy…", flush=True)
        encode_proxy(args.video, proxy)
        proxy_key = f"{args.s3_prefix}/{args.key}/_proxy.mp4"
        print("[PROGRESS] uploading proxy to S3…", flush=True)
        proxy_url = s3_cp(creds, proxy, proxy_key, "video/mp4")
        os.remove(proxy)

    print("[PROGRESS] analyzing video via Gemini (analysis + transcript)…", flush=True)
    messages = [{"role": "user", "content": [
        {"type": "text", "text": VIDEO_PROMPT},
        {"type": "video_url", "video_url": {"url": proxy_url}},
    ]}]
    data = call_openrouter(token, messages, args.model, response_json=True)
    raw = data["choices"][0]["message"]["content"]
    report_cost(data, "video-analysis")
    try:
        analysis = json.loads(raw)
    except json.JSONDecodeError:
        obj = extract_first_json(raw)
        if obj is None:
            open(os.path.join(args.output_dir, "_analysis_raw.txt"), "w").write(raw)
            sys.exit("Error: Gemini did not return JSON (saved to _analysis_raw.txt)")
        analysis = json.loads(obj)

    if analysis.get("transcript"):
        n = write_transcript_subtitles(analysis["transcript"], args.output_dir, dur)
        print(f"[PROGRESS] wrote {n} subtitle cues → video.srt / video.vtt", flush=True)

    # extract frames at every finding + visual_detail timestamp (clamped to duration)
    cap = int(dur) - 1 if dur else None
    times = set()
    for src in (analysis.get("findings", []), analysis.get("visual_details", [])):
        for item in src:
            t = item.get("time")
            if isinstance(t, (int, float)) and t >= 0:
                t = int(t)
                if cap is not None:
                    t = min(t, cap)
                times.add(t)
    shots = []
    for t in sorted(times):
        name = f"shot-{t}.jpg"
        try:
            extract_frame(args.video, t, os.path.join(args.output_dir, name))
            shots.append({"time": t, "file": name})
        except subprocess.CalledProcessError:
            print(f"[PROGRESS] skipped frame at {t}s (extract failed)", flush=True)
    print(f"[PROGRESS] extracted {len(shots)} screenshots", flush=True)

    if proxy_key and not args.keep_proxy:
        s3_rm(creds, proxy_key)  # proxy was only needed for the Gemini fetch

    result = {"analysis": analysis, "screenshots": shots,
              "transcript_file": "video.vtt", "proxy_url": proxy_url,
              "cost": (data.get("usage") or {}).get("cost")}
    print("RESULT_JSON: " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
