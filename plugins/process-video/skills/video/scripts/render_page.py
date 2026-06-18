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


def _attr_escape(s):
    """Escape a string for safe use inside an HTML attribute / text node."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_block_briefs_box(briefs, title=None, intro=None):
    """Build the "Implementation Briefs" box with rendered-preview + raw links.

    `briefs` is a list of dicts, ordered (largest → smallest):
        {"num": "01", "name": "Layout & Global Navigation",
         "changes": "~10", "file": "01-layout-navigation-brief.md"}
    `num` and `changes` are optional. `name` and `file` are required.

    The preview links carry data-md / data-title so player.html's modal renders
    them; each row also has a "raw ↗" link to the raw .md (text/plain). Returns
    "" when there are no briefs.
    """
    if not briefs:
        return ""
    title = title or "Implementation Briefs (Markdown)"
    intro = intro or (
        "One self-contained brief per block: context, requirements with "
        "timestamps, suggested sequencing and verbatim transcript excerpts. "
        "Click to open a rendered preview; “raw ↗” opens the raw markdown in a new tab."
    )
    items = []
    for b in briefs:
        f = _attr_escape(b.get("file", ""))
        name = b.get("name", b.get("label", ""))
        num = b.get("num")
        label = f"{num} · {name}" if num else name
        label_e = _attr_escape(label)
        changes = b.get("changes")
        meta = ""
        if changes:
            meta = f'{_attr_escape(changes)} changes · '
        items.append(
            '<li style="margin:5px 0">'
            f'<a href="{f}" data-md="{f}" data-title="{label_e}" '
            'style="color:#5c9aff;text-decoration:none;cursor:pointer;'
            f'border-bottom:1px dashed #5c9aff44">{label_e}</a> '
            f'<span style="color:#777;font-size:0.8rem">({meta}'
            f'<a href="{f}" target="_blank" rel="noopener" '
            'style="color:#888;text-decoration:none">raw ↗</a>)</span>'
            '</li>'
        )
    return (
        '<div id="blockBriefs" style="border:1px solid #2a3a2a;background:#141a14;'
        'border-radius:8px;padding:18px 20px;margin-bottom:28px">'
        f'<h2 style="margin:0 0 6px">\U0001F4C4 {_attr_escape(title)}</h2>'
        f'<p style="color:#aaa;font-size:0.9rem;margin:0 0 10px">{intro}</p>'
        f'<ul style="margin:0;padding-left:20px">{"".join(items)}</ul>'
        '</div><hr>'
    )


def build_analysis_block(analysis, block_briefs=None,
                         block_briefs_title=None, block_briefs_intro=None):
    """Build the developer-analysis HTML block from metadata.

    `analysis` may be a string (raw HTML body) or a dict:
        {
          "html": "<blockquote>...</blockquote>...",
          "title": "Developer Analysis",        # optional, defaults English
          "collapse_label": "Collapse",         # optional
          "expand_label": "Expand",             # optional
        }

    `block_briefs` (optional) is a list rendered as a quick-links box prepended
    to the analysis body (rendered-preview modal + raw .md links).

    Returns "" when there is no analysis content.
    """
    if not analysis:
        return ""
    if isinstance(analysis, str):
        body_html = analysis
        title = "Developer Analysis"
        collapse = "Collapse"
        expand = "Expand"
    elif isinstance(analysis, dict):
        body_html = analysis.get("html", "").strip()
        if not body_html:
            return ""
        title = analysis.get("title", "Developer Analysis")
        collapse = analysis.get("collapse_label", "Collapse")
        expand = analysis.get("expand_label", "Expand")
    else:
        return ""

    briefs_box = build_block_briefs_box(block_briefs, block_briefs_title, block_briefs_intro)
    # Only prepend if the briefs box isn't already embedded in the body html.
    if briefs_box and 'id="blockBriefs"' not in body_html:
        body_html = briefs_box + body_html

    return (
        '\n  <div class="analysis" id="analysisSection">\n'
        '    <div class="analysis-header" onclick="toggleAnalysis()">\n'
        f'      <h2>{title}</h2>\n'
        f'      <span class="analysis-toggle" id="analysisToggle"'
        f' data-collapse="{collapse}" data-expand="{expand}">[ {collapse} ]</span>\n'
        '    </div>\n'
        '    <div id="analysisContent">\n'
        f'{body_html}\n'
        '    </div>\n'
        '  </div>\n'
    )


def verify_passcode_in_html(html, passcode_hash):
    """Return True if the rendered HTML contains the expected passcode hash."""
    if not passcode_hash:
        return False
    needle = f'PASSCODE_HASH = "{passcode_hash}"'
    return needle in html


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
    analysis = metadata.get("analysis")

    block_briefs = metadata.get("block_briefs")
    block_briefs_title = metadata.get("block_briefs_title")
    block_briefs_intro = metadata.get("block_briefs_intro")

    passcode_hash = simple_hash(passcode) if passcode else ""
    tracks_html = build_subtitle_tracks(subtitle_tracks)
    chapters_json = json.dumps(chapters, ensure_ascii=False)
    analysis_block = build_analysis_block(
        analysis, block_briefs, block_briefs_title, block_briefs_intro
    )

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
        "{{ANALYSIS_BLOCK}}": analysis_block,
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

    # Mandatory passcode verification: if a passcode was requested, the rendered
    # page MUST contain the corresponding hash. Otherwise the page would be
    # silently unprotected — the exact bug we hit when re-rendering an existing
    # share without forwarding --passcode.
    if args.passcode:
        expected_hash = simple_hash(args.passcode)
        if not verify_passcode_in_html(html, expected_hash):
            print(
                f"Error: passcode was provided but the rendered page does not "
                f"contain PASSCODE_HASH = \"{expected_hash}\". The page would "
                f"be unprotected. Aborting.",
                file=sys.stderr,
            )
            try:
                os.remove(output_path)
            except OSError:
                pass
            sys.exit(2)

    print(f"Rendered {output_path} ({len(html)} bytes)")


if __name__ == "__main__":
    main()
