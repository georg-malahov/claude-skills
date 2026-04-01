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
- Auto-generated title, description, and chapter timestamps from transcript
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
