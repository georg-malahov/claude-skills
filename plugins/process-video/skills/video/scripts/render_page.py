#!/usr/bin/env python3
"""
Render video player HTML page from template + metadata.

Reads player.html template, replaces {{...}} tokens with values
from metadata.json, and writes index.html.

Usage:
    python3 render_page.py --output-dir <dir> --template <player.html> --metadata <metadata.json> [--passcode <code>] [--download-button] [--original-filename <name>]
"""

import sys
import os
import json
import argparse


def simple_hash(s):
    """JS-compatible simple hash (matches the client-side algorithm)."""
    h = 0
    for c in s:
        h = ((h << 5) - h) + ord(c)
        h &= 0xFFFFFFFF
        if h >= 0x80000000:
            h -= 0x100000000
    return str(h)


def build_subtitle_tracks(tracks):
    """Build HTML <track> elements from subtitle track list."""
    if not tracks:
        return ""
    parts = []
    for t in tracks:
        default = " default" if t.get("default") else ""
        parts.append(
            f'      <track kind="subtitles" src="{t["src"]}" '
            f'srclang="{t["srclang"]}" label="{t["label"]}"{default}>'
        )
    return "\n".join(parts)


def build_download_button(video_filename, original_filename=None):
    """Build download button HTML."""
    parts = []
    parts.append(
        f'<div class="downloads">'
        f'<a href="{video_filename}" download class="download-btn">Download Video</a>'
    )
    if original_filename:
        parts.append(
            f'<a href="{original_filename}" download class="download-btn">Download Original</a>'
        )
    parts.append("</div>")
    return "\n".join(parts)


def render(template_path, metadata, passcode=None, download_button=False, original_filename=None):
    """Render the template with metadata values."""
    with open(template_path) as f:
        html = f.read()

    title = metadata.get("title", "Shared Video")
    description = metadata.get("description", "")
    video_filename = metadata.get("video_filename", "video.mp4")
    chapters = metadata.get("chapters", [])
    subtitle_tracks = metadata.get("subtitle_tracks", [])

    passcode_hash = simple_hash(passcode) if passcode else ""
    tracks_html = build_subtitle_tracks(subtitle_tracks)
    chapters_json = json.dumps(chapters, ensure_ascii=False)

    if download_button:
        download_html = build_download_button(video_filename, original_filename)
    else:
        download_html = ""

    original_download = ""
    if original_filename and download_button:
        original_download = (
            f'<a href="{original_filename}" download class="download-btn">Download Original</a>'
        )

    replacements = {
        "{{TITLE}}": title,
        "{{DESCRIPTION}}": description,
        "{{VIDEO_FILENAME}}": video_filename,
        "{{SUBTITLE_TRACKS}}": tracks_html,
        "{{CHAPTERS_JSON}}": chapters_json,
        "{{PASSCODE_HASH}}": passcode_hash,
        "{{DOWNLOAD_BUTTON}}": download_html,
        "{{ORIGINAL_DOWNLOAD}}": original_download,
    }

    for token, value in replacements.items():
        html = html.replace(token, value)

    return html


def main():
    parser = argparse.ArgumentParser(description="Render video player page from template")
    parser.add_argument("--output-dir", required=True, help="Directory to write index.html")
    parser.add_argument("--template", required=True, help="Path to player.html template")
    parser.add_argument("--metadata", required=True, help="Path to metadata.json")
    parser.add_argument("--passcode", default=None, help="Passcode for the video")
    parser.add_argument("--download-button", action="store_true", help="Include download button")
    parser.add_argument("--original-filename", default=None, help="Original video filename for download")
    args = parser.parse_args()

    if not os.path.isfile(args.template):
        print(f"Error: template not found: {args.template}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.metadata):
        print(f"Error: metadata not found: {args.metadata}", file=sys.stderr)
        sys.exit(1)

    with open(args.metadata) as f:
        metadata = json.load(f)

    html = render(
        args.template,
        metadata,
        passcode=args.passcode,
        download_button=args.download_button,
        original_filename=args.original_filename,
    )

    output_path = os.path.join(args.output_dir, "index.html")
    with open(output_path, "w") as f:
        f.write(html)

    print(f"Rendered {output_path} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
