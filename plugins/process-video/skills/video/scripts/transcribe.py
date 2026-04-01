#!/usr/bin/env python3
"""
Transcribe audio using Deepgram Nova 3 and output SRT format.
Extracts audio from video, sends to Deepgram, generates SRT.

Usage:
    python3 transcribe.py <video_path> [--language <lang>] [--output <srt_path>] [--credential-dir <dir>]

    --language: Language code (e.g., 'en', 'de', 'fr'). Default: auto-detect.
    --output: Output SRT file path. Default: <video_name>.srt
    --credential-dir: Directory containing deepgram_token file.
"""

import sys
import os
import json
import subprocess
import argparse
import tempfile

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"
DEFAULT_CREDENTIAL_DIR = os.path.expanduser("~/.config/video-skill")


def resolve_api_key(credential_dir=None):
    """Resolve Deepgram API key from: credential file (if dir given) > env var > default file."""
    # When credential-dir is explicitly provided, prefer the file
    if credential_dir:
        token_file = os.path.join(credential_dir, "deepgram_token")
        if os.path.exists(token_file):
            with open(token_file) as f:
                token = f.read().strip()
                if token:
                    return token

    env_key = os.environ.get("DEEPGRAM_API_KEY")
    if env_key:
        return env_key

    # Fallback: check default credential dir
    token_file = os.path.join(DEFAULT_CREDENTIAL_DIR, "deepgram_token")
    if os.path.exists(token_file):
        with open(token_file) as f:
            token = f.read().strip()
            if token:
                return token

    print(
        "No Deepgram API key found. Provide one via:\n"
        "  1. Token file at: " + os.path.join(credential_dir or DEFAULT_CREDENTIAL_DIR, "deepgram_token") + "\n"
        "  2. DEEPGRAM_API_KEY environment variable",
        file=sys.stderr,
    )
    sys.exit(1)


def extract_audio(video_path, audio_path):
    """Extract audio from video as mono 16kHz WAV for optimal Deepgram processing."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vn",                    # no video
        "-acodec", "pcm_s16le",   # 16-bit PCM
        "-ar", "16000",           # 16kHz sample rate
        "-ac", "1",               # mono
        audio_path
    ]
    print(f"Extracting audio from: {os.path.basename(video_path)}", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FFmpeg error: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    print(f"Audio extracted: {size_mb:.1f} MB", flush=True)
    return audio_path


def transcribe_deepgram(audio_path, api_key, language=None):
    """Send audio to Deepgram Nova 3 and return JSON response."""
    params = [
        "model=nova-3",
        "smart_format=true",
        "utterances=true",
        "punctuate=true",
        "paragraphs=true",
    ]
    if language:
        params.append(f"language={language}")
    else:
        params.append("detect_language=true")

    url = f"{DEEPGRAM_URL}?{'&'.join(params)}"

    audio_size = os.path.getsize(audio_path)
    print(f"Sending {audio_size / (1024*1024):.1f} MB to Deepgram Nova 3...", flush=True)

    # Use curl for reliable binary upload (urllib can mangle large binary POSTs)
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST", url,
        "-H", f"Authorization: Token {api_key}",
        "-H", "Content-Type: audio/wav",
        "--data-binary", f"@{audio_path}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"curl error: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    lines = result.stdout.rsplit("\n", 1)
    body = lines[0] if len(lines) > 1 else result.stdout
    http_code = lines[1].strip() if len(lines) > 1 else "unknown"

    if http_code != "200":
        print(f"Deepgram API error {http_code}: {body}", file=sys.stderr)
        sys.exit(1)

    return json.loads(body)


def format_srt_time(seconds):
    """Convert seconds to SRT time format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_vtt_time(seconds):
    """Convert seconds to WebVTT time format: HH:MM:SS.mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def srt_to_vtt(srt_content):
    """Convert SRT content to WebVTT format."""
    vtt_lines = ["WEBVTT", ""]
    for line in srt_content.split("\n"):
        # Convert SRT timestamps (comma) to VTT (dot)
        if " --> " in line:
            line = line.replace(",", ".")
        vtt_lines.append(line)
    return "\n".join(vtt_lines)


def json_to_srt(dg_response):
    """Convert Deepgram JSON response to SRT format using utterances."""
    results = dg_response.get("results", {})

    # Prefer utterances for natural sentence-level segments
    utterances = results.get("utterances", [])
    if utterances:
        srt_lines = []
        for i, utt in enumerate(utterances, 1):
            start = format_srt_time(utt["start"])
            end = format_srt_time(utt["end"])
            text = utt["transcript"].strip()
            if text:
                srt_lines.append(f"{i}\n{start} --> {end}\n{text}\n")
        return "\n".join(srt_lines)

    # Fallback: use word-level timestamps, group into ~8-word segments
    channels = results.get("channels", [])
    if not channels:
        print("No transcription results found", file=sys.stderr)
        sys.exit(1)

    words = []
    for alt in channels[0].get("alternatives", []):
        words.extend(alt.get("words", []))

    if not words:
        print("No words found in transcription", file=sys.stderr)
        sys.exit(1)

    srt_lines = []
    segment_words = []
    segment_start = None
    idx = 1

    for word in words:
        if segment_start is None:
            segment_start = word["start"]
        segment_words.append(word["punctuated_word"])

        # Split at ~8 words or sentence-ending punctuation
        is_sentence_end = word["punctuated_word"][-1] in ".!?;" if word["punctuated_word"] else False
        if len(segment_words) >= 8 or is_sentence_end:
            start = format_srt_time(segment_start)
            end = format_srt_time(word["end"])
            text = " ".join(segment_words)
            srt_lines.append(f"{idx}\n{start} --> {end}\n{text}\n")
            idx += 1
            segment_words = []
            segment_start = None

    # Remaining words
    if segment_words:
        start = format_srt_time(segment_start)
        end = format_srt_time(words[-1]["end"])
        text = " ".join(segment_words)
        srt_lines.append(f"{idx}\n{start} --> {end}\n{text}\n")

    return "\n".join(srt_lines)


def main():
    parser = argparse.ArgumentParser(description="Transcribe video to SRT using Deepgram Nova 3")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--language", "-l", help="Language code (e.g., en, de, fr). Auto-detect if omitted.")
    parser.add_argument("--output", "-o", help="Output SRT file path")
    parser.add_argument("--credential-dir", help="Directory containing deepgram_token file")
    parser.add_argument("--json-output", help="Also save raw Deepgram JSON response to this path")
    parser.add_argument("--vtt-output", help="Also save WebVTT version to this path")
    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Video file not found: {args.video}", file=sys.stderr)
        sys.exit(1)

    api_key = resolve_api_key(args.credential_dir)
    video_base = os.path.splitext(os.path.basename(args.video))[0]
    video_dir = os.path.dirname(os.path.abspath(args.video))
    output_srt = args.output or os.path.join(video_dir, f"{video_base}.srt")

    # Extract audio to temp file
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        audio_path = tmp.name

    try:
        extract_audio(args.video, audio_path)
        dg_response = transcribe_deepgram(audio_path, api_key, args.language)

        # Optionally save raw JSON
        if args.json_output:
            with open(args.json_output, "w") as f:
                json.dump(dg_response, f, indent=2)
            print(f"Raw JSON saved: {args.json_output}", flush=True)

        # Detect language from response
        detected = dg_response.get("results", {}).get("channels", [{}])[0].get("detected_language")
        if detected:
            print(f"Detected language: {detected}", flush=True)

        # Convert to SRT
        srt_content = json_to_srt(dg_response)
        with open(output_srt, "w", encoding="utf-8") as f:
            f.write(srt_content)

        line_count = srt_content.count("\n-->")
        print(f"SRT saved: {output_srt} ({line_count} subtitle entries)", flush=True)

        # Optionally save WebVTT version
        if args.vtt_output:
            vtt_content = srt_to_vtt(srt_content)
            with open(args.vtt_output, "w", encoding="utf-8") as f:
                f.write(vtt_content)
            print(f"VTT saved: {args.vtt_output}", flush=True)

    finally:
        if os.path.exists(audio_path):
            os.unlink(audio_path)


if __name__ == "__main__":
    main()
