# process-video

Process and share videos with a unified `/video` command.

## Features

**Processing:**
- Optimize videos for web (downscale, compress, faststart)
- Transcribe audio using Deepgram Nova 3
- Generate SRT/VTT subtitles in the original language
- Translate subtitles to any language
- Burn subtitles into video with customizable styles
- Parallel processing (optimize + transcribe run concurrently)

**Sharing:**
- Share via S3 (permanent URLs) or local tunnel (pinggy/ngrok)
- Custom HTML player page with chapters, subtitles, and passcode protection
- Mandatory passcode verification at render time — when a passcode is set,
  the rendered page must contain the matching hash or the script aborts
  and removes the unprotected file (no silently public pages)
- Auto-generated title, description, and chapter timestamps from transcript
- Optional **developer analysis** section: bugs, UX issues, open questions
  and prioritized action items extracted from the transcript and embedded
  in the page with clickable timestamps that jump the player
- Short, unguessable per-video URLs (`/v/<key>`)
- Single-command flow: `/video share` processes and shares the latest video
- One approval per workflow — scripts handle everything

**Architecture:**
- Entry-point scripts for each workflow (process_and_share, share_existing, upload_s3)
- Credentials stored persistently at `~/.config/video-skill/` (never exposed in CLI args)
- Preferences saved across sessions for consistent defaults

## Requirements

- `ffmpeg` and `ffprobe` installed (`brew install ffmpeg` on macOS)
- Python 3
- `aws` CLI (for S3 uploads)
- Deepgram API key (saved to `~/.config/video-skill/deepgram_token`)
- S3 credentials (saved to `~/.config/video-skill/s3_credentials`)

## Commands

| Command | Description |
|---------|-------------|
| `/video` | Interactive processing (full workflow) |
| `/video process <path>` | Process a specific file interactively |
| `/video share` | Process latest video + share (silent mode) |
| `/video share <path>` | Process and share a specific file |
| `/video start` | Start the share server + tunnel |
| `/video stop` | Stop sharing |
| `/video status` | List all shared videos with URLs and passcodes |
| `/video copy <name>` | Copy a video's link + passcode to clipboard |
| `/video remove <name>` | Remove a video from sharing |

## Scripts

| Script | Purpose |
|--------|---------|
| `process_and_share.py` | Main workflow: optimize + transcribe + render + upload |
| `share_existing.py` | Share a pre-processed folder |
| `upload_s3.py` | Parallel S3 upload with content types |
| `render_page.py` | Generate HTML player from template + metadata |
| `manage_registry.py` | Share registry CRUD + migration |
| `transcribe.py` | Deepgram Nova 3 transcription → SRT + VTT |
| `burn_subtitles.py` | Burn subtitles into video via ffmpeg |
| `share_server.py` | Local HTTP server with `/v/<key>` routing |

## Subtitle Styles

| Style          | Font            | Size | Bold | Outline | Shadow |
|----------------|-----------------|------|------|---------|--------|
| Classic        | Arial           | 18   | 1    | 1       | 1      |
| Modern         | Helvetica Neue  | 18   | 1    | 1       | 1      |
| Cinematic      | Georgia         | 18   | 1    | 0       | 0      |
| High Contrast  | Arial           | 22   | 2    | 2       | 1      |

## Developer Analysis

For screencasts that review a tool, comment on bugs, or give product/UX
feedback, the skill can embed a structured **Developer Analysis** section
in the rendered page. When enabled, the model reads the full transcript
and produces:

- **Bugs** with severity (`high` / `mittel` / `niedrig` / `critical`),
  in-video timestamps, description, impact and suggested action
- **UX issues** with priority and short rationale
- **Open questions** for the product owner / tester
- **Action items** grouped into critical / high / medium / low priority
  buckets
- A short summary box

Timestamps in the analysis are clickable and jump the player to that
moment.

To enable, set `developer_analysis: true` in
`~/.config/video-skill/preferences.json`, pick the option in the
interactive flow (Step 3 → Q3), or pass `--developer-analysis` to
`process_and_share.py` directly. Off by default — for general
screencasts the analysis would be noise.

## Passcode protection

Passcodes are passed via `--passcode <code>` to `process_and_share.py`
or `share_existing.py`. The HTML player gates content behind a
client-side passcode check (cleartext hash, not cryptographic — meant
to keep links unguessable, not to protect strong secrets).

`render_page.py` enforces a hard rule: **if `--passcode` is provided,
the rendered HTML must contain the matching hash**. If the substitution
silently failed for any reason (template missing the placeholder,
re-render forgetting to forward the passcode, etc.), the script exits
with code 2 and removes the bad output file — so an unprotected page
can't slip out. Always forward the passcode when re-rendering an
existing share; you can look it up in
`<share_folder>/.share_registry.json`.
