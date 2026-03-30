#!/usr/bin/env python3
"""
Burn SRT subtitles into a video using ffmpeg with customizable styles.
Shows progress every 10 seconds and estimates remaining time.

Usage:
    python3 burn_subtitles.py <video_path> <srt_path> [options]

Options:
    --output <path>         Output video path (default: <video>_subtitled.<ext>)
    --font <name>           Font name (default: Arial)
    --fontsize <n>          Font size (default: 24)
    --fontcolor <hex>       Primary color in &HBBGGRR format (default: &H00FFFFFF - white)
    --outlinecolor <hex>    Outline color (default: &H00000000 - black)
    --outline <n>           Outline width (default: 2)
    --shadow <n>            Shadow depth (default: 1)
    --bold <0|1>            Bold text (default: 1)
    --alignment <n>         Position: 1=bottom-left, 2=bottom-center, 5=top-left, 6=top-center (default: 2)
    --margin-v <n>          Vertical margin from edge (default: 30)
    --second-srt <path>     Second SRT file to burn (e.g., original language)
    --second-alignment <n>  Alignment for second SRT (default: 6, top-center)
    --second-fontsize <n>   Font size for second SRT (default: 20)
"""

import sys
import os
import subprocess
import argparse
import time
import re
import select
import fcntl


def get_video_duration(video_path):
    """Get video duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json",
        "-show_format", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    import json
    data = json.loads(result.stdout)
    return float(data.get("format", {}).get("duration", 0))


def escape_path_for_subtitles(path):
    """Escape special characters in file path for ffmpeg subtitle filter."""
    # For the subtitles filter, we need to escape colons, backslashes, and single quotes
    path = path.replace("\\", "\\\\\\\\")
    path = path.replace(":", "\\\\:")
    path = path.replace("'", "'\\''")
    # Also escape brackets and other special chars
    path = path.replace("[", "\\[")
    path = path.replace("]", "\\]")
    return path


def build_style_override(args):
    """Build ASS style override string from arguments."""
    parts = [
        f"FontName={args.font}",
        f"FontSize={args.fontsize}",
        f"PrimaryColour={args.fontcolor}",
        f"OutlineColour={args.outlinecolor}",
        f"Outline={args.outline}",
        f"Shadow={args.shadow}",
        f"Bold={args.bold}",
        f"Alignment={args.alignment}",
        f"MarginV={args.margin_v}",
    ]
    return ",".join(parts)


def burn_subtitles(video_path, srt_path, output_path, args, second_srt=None):
    """Burn subtitles into video with progress reporting."""
    duration = get_video_duration(video_path)
    if not duration:
        print("Warning: Could not determine video duration", flush=True)
        duration = 0

    escaped_srt = escape_path_for_subtitles(os.path.abspath(srt_path))
    style = build_style_override(args)

    # Build filter
    filter_parts = [f"subtitles='{escaped_srt}':force_style='{style}'"]

    if second_srt:
        escaped_second = escape_path_for_subtitles(os.path.abspath(second_srt))
        second_style_parts = [
            f"FontName={args.font}",
            f"FontSize={args.second_fontsize}",
            f"PrimaryColour={args.fontcolor}",
            f"OutlineColour={args.outlinecolor}",
            f"Outline={args.outline}",
            f"Shadow={args.shadow}",
            f"Bold=0",
            f"Alignment={args.second_alignment}",
            f"MarginV={args.margin_v}",
        ]
        second_style = ",".join(second_style_parts)
        filter_parts.append(f"subtitles='{escaped_second}':force_style='{second_style}'")

    vf = ",".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(args.crf),
        "-preset", "medium",
        "-movflags", "+faststart",  # Web optimization
        "-c:a", "copy",             # Don't re-encode audio
        "-progress", "pipe:1",      # Progress to stdout
        output_path
    ]

    print(f"Burning subtitles into video...", flush=True)
    print(f"Output: {output_path}", flush=True)
    if duration:
        print(f"Video duration: {duration:.0f}s", flush=True)
    print("---", flush=True)

    start_time = time.time()
    last_report = 0

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    current_time_us = 0
    try:
        for line in process.stdout:
            line = line.strip()
            if line.startswith("out_time_us="):
                try:
                    current_time_us = int(line.split("=")[1])
                except (ValueError, IndexError):
                    pass

            if line == "progress=continue" or line == "progress=end":
                now = time.time()
                elapsed = now - start_time
                if now - last_report >= 10 or line == "progress=end":
                    current_secs = current_time_us / 1_000_000
                    if duration > 0:
                        pct = min(100, (current_secs / duration) * 100)
                        if pct > 0:
                            eta = (elapsed / pct) * (100 - pct)
                            eta_min = int(eta // 60)
                            eta_sec = int(eta % 60)
                            print(
                                f"Progress: {pct:.1f}% | "
                                f"Elapsed: {int(elapsed)}s | "
                                f"ETA: {eta_min}m {eta_sec}s",
                                flush=True
                            )
                        else:
                            print(f"Progress: starting... | Elapsed: {int(elapsed)}s", flush=True)
                    else:
                        print(f"Processed: {current_secs:.0f}s | Elapsed: {int(elapsed)}s", flush=True)
                    last_report = now

        process.wait()
    except KeyboardInterrupt:
        process.kill()
        print("\nCancelled!", flush=True)
        sys.exit(1)

    if process.returncode != 0:
        stderr = process.stderr.read()
        print(f"FFmpeg error (exit {process.returncode}):\n{stderr}", file=sys.stderr)
        sys.exit(1)

    total_time = time.time() - start_time
    output_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"---\nDone! Completed in {int(total_time)}s", flush=True)
    print(f"Output size: {output_size:.1f} MB", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Burn SRT subtitles into video")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("srt", help="Path to SRT subtitle file")
    parser.add_argument("--output", "-o", help="Output video path")
    parser.add_argument("--font", default="Arial", help="Font name")
    parser.add_argument("--fontsize", type=int, default=18, help="Font size")
    parser.add_argument("--fontcolor", default="&H00FFFFFF", help="Primary color (&HBBGGRR)")
    parser.add_argument("--outlinecolor", default="&H00000000", help="Outline color (&HBBGGRR)")
    parser.add_argument("--outline", type=int, default=2, help="Outline width")
    parser.add_argument("--shadow", type=int, default=1, help="Shadow depth")
    parser.add_argument("--bold", type=int, default=1, choices=[0, 1], help="Bold text")
    parser.add_argument("--alignment", type=int, default=2, help="Subtitle alignment")
    parser.add_argument("--margin-v", type=int, default=30, help="Vertical margin")
    parser.add_argument("--second-srt", help="Second SRT file for dual subtitles")
    parser.add_argument("--second-alignment", type=int, default=6, help="Second SRT alignment")
    parser.add_argument("--second-fontsize", type=int, default=20, help="Second SRT font size")
    parser.add_argument("--crf", type=int, default=23, help="CRF quality (18=near-lossless, 23=default, 28=smaller)")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Video not found: {args.video}", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(args.srt):
        print(f"SRT not found: {args.srt}", file=sys.stderr)
        sys.exit(1)

    if not args.output:
        base, ext = os.path.splitext(args.video)
        args.output = f"{base}_subtitled{ext}"

    burn_subtitles(args.video, args.srt, args.output, args, args.second_srt)


if __name__ == "__main__":
    main()
