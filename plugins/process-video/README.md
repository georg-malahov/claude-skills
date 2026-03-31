# process-video

Process and share videos with a unified `/video` command.

## Features

**Processing:**
- Optimize videos for web (downscale, compress, faststart)
- Transcribe audio using Deepgram Nova 3
- Generate SRT/VTT subtitles in the original language
- Translate subtitles to any language
- Burn subtitles into video with customizable styles
- Interactive review and editing of transcripts before burning

**Sharing:**
- Share videos via local tunnel (pinggy/ngrok) with short, unguessable URLs
- Custom HTML player page with chapters, subtitles, and passcode protection
- Auto-generated title, description, and chapter timestamps from transcript
- Single server manages all shared videos
- One-command flow: `/video share` processes and shares the latest video

## Requirements

- `ffmpeg` and `ffprobe` installed (`brew install ffmpeg` on macOS)
- Python 3
- Deepgram API key (the skill will ask for one on first use and save it locally)

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

## Subtitle Styles

| Style          | Font            | Size | Bold | Outline | Shadow |
|----------------|-----------------|------|------|---------|--------|
| Classic        | Arial           | 18   | 1    | 1       | 1      |
| Modern         | Helvetica Neue  | 18   | 1    | 1       | 1      |
| Cinematic      | Georgia         | 18   | 1    | 0       | 0      |
| High Contrast  | Arial           | 22   | 2    | 2       | 1      |
