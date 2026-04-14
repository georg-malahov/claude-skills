#!/usr/bin/env python3
"""
Main workflow: process a video and share it.

Two-phase execution:
  Phase 1: Optimize video + transcribe audio (parallel)
           Then print transcript and wait for metadata.json
  Phase 2: Render player page + upload to S3 (parallel)
           Print final URL

Usage:
    python3 process_and_share.py <video_path> \\
        --output-dir <dir> \\
        --credential-dir ~/.config/video-skill \\
        --share-folder <dir> \\
        [--resolution 1080p] [--crf 23] [--preset medium] [--audio aac-128k] \\
        [--subtitles track|burn|none] [--subtitle-lang <code>] \\
        [--share s3|tunnel|both|none] [--passcode <code>] \\
        [--title <override>] [--context <description>]
"""

import sys
import os
import json
import argparse
import subprocess
import time
import shutil
from concurrent.futures import ThreadPoolExecutor, Future
from datetime import datetime

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


def run_cmd(cmd, desc=None, env=None, timeout=600):
    """Run a subprocess, return (success, stdout, stderr)."""
    if desc:
        print(f"[PROGRESS] {desc}", flush=True)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout after {timeout}s"


def get_video_info(video_path):
    """Get video duration, resolution, and audio track info via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", "-show_streams", video_path,
    ]
    ok, stdout, stderr = run_cmd(cmd)
    if not ok:
        return {}
    info = json.loads(stdout)
    result = {}
    for stream in info.get("streams", []):
        if stream.get("codec_type") == "video":
            result["width"] = stream.get("width", 0)
            result["height"] = stream.get("height", 0)
        if stream.get("codec_type") == "audio":
            result["has_audio"] = True
    result["duration"] = float(info.get("format", {}).get("duration", 0))
    return result


def optimize_video(video_path, output_path, resolution, crf, preset, audio):
    """Optimize video with ffmpeg. Returns (success, output_path)."""
    cmd = ["ffmpeg", "-y", "-i", video_path]

    # Video filter for resolution
    if resolution == "1080p":
        cmd += ["-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2"]
    elif resolution == "720p":
        cmd += ["-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2"]
    # "keep" = no scale filter

    cmd += ["-c:v", "libx264", "-crf", str(crf), "-preset", preset, "-movflags", "+faststart"]

    # Audio settings
    if audio == "copy":
        cmd += ["-c:a", "copy"]
    elif audio.startswith("aac-"):
        bitrate = audio.split("-")[1]
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    else:
        cmd += ["-c:a", "aac", "-b:a", "128k"]

    cmd.append(output_path)

    start = time.time()
    ok, stdout, stderr = run_cmd(cmd, f"Optimizing video ({resolution}, CRF {crf})...", timeout=1200)
    elapsed = time.time() - start

    if ok:
        size_mb = os.path.getsize(output_path) / (1024 * 1024)
        print(f"[PROGRESS] Video optimized: {size_mb:.1f} MB ({elapsed:.0f}s)", flush=True)
    else:
        print(f"[ERROR] Video optimization failed: {stderr[:500]}", flush=True)

    return ok


def extract_audio(video_path, audio_path):
    """Extract audio as mono 16kHz WAV."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path,
    ]
    start = time.time()
    ok, stdout, stderr = run_cmd(cmd, "Extracting audio...")
    elapsed = time.time() - start
    if ok:
        print(f"[PROGRESS] Audio extracted ({elapsed:.1f}s)", flush=True)
    else:
        print(f"[ERROR] Audio extraction failed: {stderr[:500]}", flush=True)
    return ok


def transcribe(video_path, output_dir, video_base, credential_dir, language=None):
    """Run transcribe.py to generate SRT + VTT + raw JSON."""
    srt_path = os.path.join(output_dir, f"{video_base}.srt")
    vtt_path = os.path.join(output_dir, f"{video_base}.vtt")
    json_path = os.path.join(output_dir, "deepgram_raw.json")

    cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "transcribe.py"),
        video_path,
        "--output", srt_path,
        "--vtt-output", vtt_path,
        "--json-output", json_path,
        "--credential-dir", credential_dir,
    ]
    if language:
        cmd += ["--language", language]

    start = time.time()
    print("[PROGRESS] Transcribing via Deepgram Nova 3...", flush=True)
    ok, stdout, stderr = run_cmd(cmd, timeout=300)
    elapsed = time.time() - start

    if ok:
        # Count entries
        if os.path.exists(srt_path):
            with open(srt_path) as f:
                entries = f.read().count("\n-->") + f.read().count(" --> ")
            # Re-read for accurate count
            with open(srt_path) as f:
                content = f.read()
                entries = content.count(" --> ")
            print(f"[PROGRESS] Transcription complete: {entries} entries ({elapsed:.0f}s)", flush=True)
        if stdout.strip():
            print(stdout.strip(), flush=True)
    else:
        combined = (stdout + "\n" + stderr).strip()
        print(f"[ERROR] Transcription failed: {combined[:500]}", flush=True)

    return ok, srt_path, vtt_path, json_path


def read_transcript_preview(srt_path, max_chars=500):
    """Read first N chars of SRT file for metadata generation."""
    if not os.path.exists(srt_path):
        return ""
    with open(srt_path) as f:
        content = f.read()
    # Extract just the text (skip timestamps and numbers)
    lines = []
    for line in content.split("\n"):
        line = line.strip()
        if not line or line.isdigit() or " --> " in line:
            continue
        lines.append(line)
    text = " ".join(lines)
    return text[:max_chars]


def generate_fallback_metadata(video_base, srt_path, vtt_path, deepgram_json_path):
    """Generate heuristic metadata from Deepgram JSON when Claude doesn't respond."""
    metadata = {
        "title": video_base.replace("_", " ").replace("-", " ").title(),
        "description": "",
        "chapters": [{"time": 0, "label": "Start"}],
        "video_filename": f"{video_base}_1080p.mp4",
        "subtitle_tracks": [],
    }

    if vtt_path and os.path.exists(vtt_path):
        metadata["subtitle_tracks"].append({
            "src": os.path.basename(vtt_path),
            "srclang": "en",
            "label": "Subtitles",
            "default": True,
        })

    # Try to extract paragraphs from Deepgram JSON for chapters
    if os.path.exists(deepgram_json_path):
        try:
            with open(deepgram_json_path) as f:
                dg = json.load(f)
            paragraphs = (dg.get("results", {}).get("channels", [{}])[0]
                          .get("alternatives", [{}])[0].get("paragraphs", {})
                          .get("paragraphs", []))
            if paragraphs:
                chapters = []
                for i, para in enumerate(paragraphs):
                    sentences = para.get("sentences", [])
                    if sentences:
                        start = sentences[0].get("start", 0)
                        label = sentences[0].get("text", f"Part {i+1}")[:60]
                        chapters.append({"time": round(start, 1), "label": label})
                if chapters:
                    metadata["chapters"] = chapters

                # Use first paragraph as description
                if paragraphs[0].get("sentences"):
                    desc_parts = [s.get("text", "") for s in paragraphs[0]["sentences"]]
                    metadata["description"] = " ".join(desc_parts)[:300]
        except (json.JSONDecodeError, KeyError, IndexError):
            pass

    return metadata


def wait_for_metadata(output_dir, timeout=120):
    """Poll for metadata.json, return path when found or None on timeout."""
    metadata_path = os.path.join(output_dir, "metadata.json")
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(metadata_path):
            # Give a moment for write to complete
            time.sleep(0.5)
            try:
                with open(metadata_path) as f:
                    json.load(f)  # Validate JSON
                return metadata_path
            except (json.JSONDecodeError, IOError):
                pass  # File still being written
        time.sleep(2)
    return None


def render_page(output_dir, passcode, download_button=True, original_filename=None):
    """Run render_page.py to generate index.html."""
    template = os.path.join(SCRIPTS_DIR, "player.html")
    metadata_path = os.path.join(output_dir, "metadata.json")

    cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "render_page.py"),
        "--output-dir", output_dir,
        "--template", template,
        "--metadata", metadata_path,
    ]
    if passcode:
        cmd += ["--passcode", passcode]
    if download_button:
        cmd.append("--download-button")
    if original_filename:
        cmd += ["--original-filename", original_filename]

    ok, stdout, stderr = run_cmd(cmd, "Rendering player page...")
    if not ok:
        print(f"[ERROR] Page rendering failed: {stderr[:500]}", flush=True)
    elif stdout.strip():
        print(f"[PROGRESS] {stdout.strip()}", flush=True)
    return ok


def register_video(share_folder, folder_name, title, passcode, method, s3_url=None):
    """Run manage_registry.py to register the video."""
    cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "manage_registry.py"),
        "add",
        "--share-folder", share_folder,
        "--folder", folder_name,
        "--title", title,
        "--method", method,
    ]
    if passcode:
        cmd += ["--passcode", passcode]
    if s3_url:
        cmd += ["--s3-url", s3_url]

    ok, stdout, stderr = run_cmd(cmd)
    if ok and stdout.strip():
        return json.loads(stdout.strip())
    print(f"[ERROR] Registration failed: {stderr[:500]}", flush=True)
    return None


def upload_to_s3(output_dir, key, credential_dir):
    """Run upload_s3.py to upload files."""
    cmd = [
        sys.executable, os.path.join(SCRIPTS_DIR, "upload_s3.py"),
        output_dir,
        "--key", key,
        "--credential-dir", credential_dir,
    ]
    ok, stdout, stderr = run_cmd(cmd, timeout=600)
    if stdout.strip():
        print(stdout.strip(), flush=True)
    if not ok:
        print(f"[ERROR] S3 upload failed: {stderr[:500]}", flush=True)
    # Extract URL from output
    for line in stdout.split("\n"):
        if line.startswith("[URL]"):
            return line.split(" ", 1)[1].strip()
    return None


def copy_to_clipboard(text):
    """Copy text to macOS clipboard."""
    try:
        subprocess.run(["pbcopy"], input=text, text=True, timeout=5)
        return True
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Process and share a video")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--output-dir", required=True, help="Output directory for processed files")
    parser.add_argument("--credential-dir", default=os.path.expanduser("~/.config/video-skill"))
    parser.add_argument("--share-folder", required=True, help="Root folder for shared videos")
    parser.add_argument("--resolution", default="1080p", choices=["1080p", "720p", "keep"])
    parser.add_argument("--crf", type=int, default=23)
    parser.add_argument("--preset", default="medium")
    parser.add_argument("--audio", default="aac-128k")
    parser.add_argument("--subtitles", default="track", choices=["track", "burn", "none"])
    parser.add_argument("--subtitle-lang", default=None, help="Language code for transcription")
    parser.add_argument("--share", default="s3", choices=["s3", "tunnel", "both", "none"])
    parser.add_argument("--passcode", default=None)
    parser.add_argument("--title", default=None, help="Override title (skip metadata wait)")
    parser.add_argument("--context", default=None, help="Extra context for metadata generation")
    parser.add_argument("--download-button", action="store_true", default=True)
    parser.add_argument("--no-download-button", action="store_true")
    parser.add_argument(
        "--developer-analysis",
        action="store_true",
        default=False,
        help="Ask the agent to also generate a developer-analysis block (bugs / UX / priorities).",
    )
    args = parser.parse_args()

    if args.no_download_button:
        args.download_button = False

    if not os.path.isfile(args.video):
        print(f"Error: video not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    # Setup
    video_path = os.path.abspath(args.video)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    video_base = os.path.splitext(os.path.basename(video_path))[0]
    optimized_name = f"{video_base}_1080p.mp4"
    optimized_path = os.path.join(output_dir, optimized_name)

    # Get video info
    info = get_video_info(video_path)
    has_audio = info.get("has_audio", False)
    duration = info.get("duration", 0)

    print(f"[PROGRESS] Starting: {os.path.basename(video_path)} "
          f"({info.get('width', '?')}x{info.get('height', '?')}, {duration:.0f}s)", flush=True)

    # ── Phase 1: Optimize + Transcribe (parallel where possible) ──

    with ThreadPoolExecutor(max_workers=3) as pool:
        # Start video optimization (skip if output already exists)
        if os.path.isfile(optimized_path) and os.path.getsize(optimized_path) > 0:
            size_mb = os.path.getsize(optimized_path) / (1024 * 1024)
            print(f"[PROGRESS] Optimized video exists: {optimized_name} ({size_mb:.1f} MB), skipping.", flush=True)

            class _Done:
                def result(self):
                    return True
            opt_future = _Done()
        else:
            opt_future = pool.submit(optimize_video, video_path, optimized_path,
                                     args.resolution, args.crf, args.preset, args.audio)

        # Start transcription (needs original video for best audio quality)
        transcribe_future = None
        srt_path = vtt_path = json_path = None

        if has_audio and args.subtitles != "none":
            transcribe_future = pool.submit(
                transcribe, video_path, output_dir, video_base,
                args.credential_dir, args.subtitle_lang,
            )

        # Wait for optimization
        opt_ok = opt_future.result()
        if not opt_ok:
            print("[ERROR] Video optimization failed. Aborting.", flush=True)
            sys.exit(1)

        # Wait for transcription
        if transcribe_future:
            t_ok, srt_path, vtt_path, json_path = transcribe_future.result()
            if not t_ok:
                print("[WARNING] Transcription failed. Continuing without subtitles.", flush=True)
                srt_path = vtt_path = json_path = None

    # ── Metadata generation ──

    if args.title:
        # Title override provided — generate metadata directly
        metadata = {
            "title": args.title,
            "description": args.context or "",
            "chapters": [{"time": 0, "label": "Start"}],
            "video_filename": optimized_name,
            "subtitle_tracks": [],
        }
        if vtt_path and os.path.exists(vtt_path):
            metadata["subtitle_tracks"].append({
                "src": os.path.basename(vtt_path),
                "srclang": args.subtitle_lang or "en",
                "label": "Subtitles",
                "default": True,
            })
        metadata_path = os.path.join(output_dir, "metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print("[PROGRESS] Using provided title, skipping metadata wait.", flush=True)
    else:
        # Print transcript for Claude to generate metadata
        if srt_path and os.path.exists(srt_path):
            preview = read_transcript_preview(srt_path)
            print(f"\nTRANSCRIPT_PREVIEW:\n{preview}\n---", flush=True)

        # Include helpful info for Claude
        info_for_claude = {
            "video_filename": optimized_name,
            "video_base": video_base,
            "has_subtitles": vtt_path is not None and os.path.exists(vtt_path),
            "vtt_filename": os.path.basename(vtt_path) if vtt_path else None,
            "subtitle_lang": args.subtitle_lang,
            "context": args.context,
            "developer_analysis": bool(args.developer_analysis),
        }
        print(f"METADATA_INFO:{json.dumps(info_for_claude)}", flush=True)
        print(f"METADATA_READY:{output_dir}", flush=True)

        # Wait for Claude to write metadata.json
        print("[PROGRESS] Waiting for metadata generation...", flush=True)
        metadata_path = wait_for_metadata(output_dir, timeout=120)

        if metadata_path is None:
            print("[WARNING] Metadata timeout. Using heuristic fallback.", flush=True)
            metadata = generate_fallback_metadata(video_base, srt_path, vtt_path, json_path or "")
            metadata_path = os.path.join(output_dir, "metadata.json")
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)

    # ── Phase 2: Render page + Register + Upload ──

    # Burn subtitles if requested (before rendering page)
    if args.subtitles == "burn" and srt_path and os.path.exists(srt_path):
        burned_name = f"{video_base}_subtitled.mp4"
        burned_path = os.path.join(output_dir, burned_name)
        cmd = [
            sys.executable, os.path.join(SCRIPTS_DIR, "burn_subtitles.py"),
            optimized_path, srt_path,
            "--output", burned_path,
            "--crf", str(args.crf),
        ]
        print("[PROGRESS] Burning subtitles into video...", flush=True)
        ok, stdout, stderr = run_cmd(cmd, timeout=1200)
        if ok:
            print(f"[PROGRESS] Subtitles burned: {burned_name}", flush=True)
            # Update metadata to point to burned version
            with open(metadata_path) as f:
                metadata = json.load(f)
            metadata["video_filename"] = burned_name
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
        else:
            print(f"[WARNING] Subtitle burn failed, using video without burned subs: {stderr[:300]}", flush=True)

    # Render HTML page
    render_ok = render_page(output_dir, args.passcode, args.download_button)
    if not render_ok:
        print("[ERROR] Failed to render player page.", flush=True)
        sys.exit(1)

    # Read title from metadata for registry
    with open(metadata_path) as f:
        metadata = json.load(f)
    title = metadata.get("title", video_base)

    # Determine folder name relative to share_folder
    folder_name = os.path.basename(output_dir)

    # Register in share registry
    reg_result = register_video(
        args.share_folder, folder_name, title, args.passcode, args.share,
    )
    if not reg_result:
        print("[ERROR] Failed to register video.", flush=True)
        sys.exit(1)

    key = reg_result["key"]
    print(f"[PROGRESS] Registered with key: {key}", flush=True)

    # Upload to S3 if requested
    s3_url = None
    if args.share in ("s3", "both"):
        s3_url = upload_to_s3(output_dir, key, args.credential_dir)
        if s3_url:
            # Update registry with S3 URL
            register_video(
                args.share_folder, folder_name, title, args.passcode,
                args.share, s3_url=s3_url,
            )

    # ── Final output ──

    share_url = s3_url or f"(tunnel URL — start with /video start)"
    clipboard_text = f"{title}\n{share_url}"
    if args.passcode:
        clipboard_text += f"\nPasscode: {args.passcode}"

    copy_to_clipboard(clipboard_text)

    print(f"\n{'='*60}", flush=True)
    print(f"[DONE] Video processed and shared!", flush=True)
    print(f"  Title: {title}", flush=True)
    print(f"  Key: {key}", flush=True)
    print(f"  URL: {share_url}", flush=True)
    if args.passcode:
        print(f"  Passcode: {args.passcode}", flush=True)
    print(f"  Copied to clipboard.", flush=True)
    print(f"{'='*60}", flush=True)


if __name__ == "__main__":
    main()
