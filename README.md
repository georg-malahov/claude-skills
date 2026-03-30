# Claude Skills

A collection of Claude Code skills for video processing, transcription, and more.

## Installation

Add the marketplace and install the skill you need:

```
/plugin marketplace add georg-malahov/claude-skills
/plugin install process-video@georg-malahov-claude-skills
```

## Available Skills

### process-video

Process videos with optimization, subtitles, transcription, and translation.

**Features:**
- Optimize videos for web (downscale, compress, faststart)
- Transcribe audio using Deepgram Nova 3
- Generate SRT subtitles in the original language
- Translate subtitles to any language
- Burn subtitles into video with customizable styles
- Interactive review and editing of transcripts before burning
- Full comparison summary (original vs output)

**Requirements:**
- `ffmpeg` and `ffprobe` installed (`brew install ffmpeg` on macOS)
- Python 3
- Deepgram API key (the skill will ask for one on first use and save it locally)

**Usage:**

Invoke with `/process-video` or just ask Claude to process a video in any folder.

The skill will guide you through:
1. Language preference for communication
2. Video selection (shows 3 newest files)
3. Optimization settings (resolution, quality, speed — explained in plain language)
4. Subtitle options (original, translated, or both as separate videos)
5. Style selection with visual previews
6. Transcript review and editing
7. Final processing with progress tracking

## Adding New Skills

Each skill lives in `plugins/<skill-name>/` with this structure:

```
plugins/<skill-name>/
├── .claude-plugin/
│   └── plugin.json
└── skills/
    └── <skill-name>/
        ├── SKILL.md
        └── scripts/       (optional)
```

After adding a new skill, register it in `.claude-plugin/marketplace.json`.
