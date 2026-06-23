#!/usr/bin/env python3
"""Shared subtitle helpers — timestamp formatting, cue→SRT/VTT, and the
[MM:SS]-marker transcript parser used by the Gemini engine.

A "cue" is a (start_seconds, end_seconds, text) tuple.
"""
import re


def format_srt_time(seconds):
    """HH:MM:SS,mmm"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_vtt_time(seconds):
    """HH:MM:SS.mmm"""
    return format_srt_time(seconds).replace(",", ".")


def srt_to_vtt(srt_content):
    """Convert SRT text to WebVTT (timestamps comma→dot, WEBVTT header)."""
    out = ["WEBVTT", ""]
    for line in srt_content.split("\n"):
        if " --> " in line:
            line = line.replace(",", ".")
        out.append(line)
    return "\n".join(out)


def cues_to_srt(cues):
    """Render (start, end, text) cues to SRT text."""
    lines = []
    for i, (a, b, text) in enumerate(cues, 1):
        lines.append(f"{i}\n{format_srt_time(a)} --> {format_srt_time(b)}\n{text}\n")
    return "\n".join(lines)


def cues_to_vtt(cues):
    """Render (start, end, text) cues to WebVTT text."""
    out = ["WEBVTT", ""]
    for a, b, text in cues:
        out.append(f"{format_vtt_time(a)} --> {format_vtt_time(b)}")
        out.append(text)
        out.append("")
    return "\n".join(out)


def write_subtitles(out_dir, cues, basename="video"):
    """Write <basename>.srt and <basename>.vtt into out_dir. Returns cue count."""
    import os
    open(os.path.join(out_dir, f"{basename}.srt"), "w").write(cues_to_srt(cues))
    open(os.path.join(out_dir, f"{basename}.vtt"), "w").write(cues_to_vtt(cues))
    return len(cues)


_MARKER = re.compile(r"\[(\d{1,2}):(\d{2})\]")


def markers_to_cues(text, video_end=0):
    """Parse a flowing transcript with inline [MM:SS] markers into cues.

    Each marker is the END of the preceding chunk; the cue start is the previous
    marker (0 for the first). Normalises ordering, min duration, and clamps to
    video_end (if given). Coarse by nature — Gemini markers are approximate.
    """
    text = text.split("---")[0]
    cues, prev, last_end = [], 0.0, 0
    for m in _MARKER.finditer(text):
        t = int(m.group(1)) * 60 + int(m.group(2))
        chunk = re.sub(r"\s+", " ", text[last_end:m.start()]).strip()
        last_end = m.end()
        if chunk:
            cues.append([prev, float(t), chunk])
        prev = float(t)
    tail = re.sub(r"\s+", " ", text[last_end:]).strip().strip(".")
    if tail:
        cues.append([prev, min(prev + 3, video_end or prev + 3), tail])

    for c in cues:
        if c[1] <= c[0]:
            c[1] = c[0] + 1.5
        if video_end:
            c[1] = min(c[1], video_end)
    for i in range(len(cues) - 1):
        if cues[i][1] > cues[i + 1][0]:
            cues[i][1] = cues[i + 1][0]
        if cues[i][1] - cues[i][0] < 0.6:
            cues[i][1] = cues[i][0] + 0.6
    return [tuple(c) for c in cues]
