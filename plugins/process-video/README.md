# process-video

Process videos with optimization, subtitles, transcription, and translation.

## Features

- Optimize videos for web (downscale, compress, faststart)
- Transcribe audio using Deepgram Nova 3
- Generate SRT subtitles in the original language
- Translate subtitles to any language
- Burn subtitles into video with customizable styles
- Interactive review and editing of transcripts before burning
- Full comparison summary (original vs output)

## Requirements

- `ffmpeg` and `ffprobe` installed (`brew install ffmpeg` on macOS)
- Python 3
- Deepgram API key (the skill will ask for one on first use and save it locally)

## Usage

Invoke with `/process-video` or just ask Claude to process a video in any folder.

The skill will guide you through:
1. Language preference for communication
2. Video selection (shows 3 newest files)
3. Optimization settings (resolution, quality, speed — explained in plain language)
4. Subtitle options (original, translated, or both as separate videos)
5. Style selection with visual previews
6. Transcript review and editing
7. Final processing with progress tracking

## Subtitle Styles

| Style          | Font            | Size | Bold | Outline | Shadow |
|----------------|-----------------|------|------|---------|--------|
| Classic        | Arial           | 18   | 1    | 1       | 1      |
| Modern         | Helvetica Neue  | 18   | 1    | 1       | 1      |
| Cinematic      | Georgia         | 18   | 1    | 0       | 0      |
| High Contrast  | Arial           | 22   | 2    | 2       | 1      |
