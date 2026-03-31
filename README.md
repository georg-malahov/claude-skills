# Claude Skills

A marketplace of Claude Code plugins for video processing, transcription, and more.

## Installation

Add the marketplace and install the plugin you need:

```
/plugin marketplace add georg-malahov/claude-skills
/plugin install process-video@georg-malahov-claude-skills
```

## Available Plugins

| Plugin | Description |
|--------|-------------|
| [process-video](plugins/process-video/) | Optimize videos for web, transcribe audio, add/translate subtitles, burn into video |

## Adding New Plugins

Each plugin lives in `plugins/<plugin-name>/` with this structure:

```
plugins/<plugin-name>/
├── .claude-plugin/
│   └── plugin.json
├── README.md
└── skills/
    └── <skill-name>/
        ├── SKILL.md
        └── scripts/       (optional)
```

After adding a new plugin, register it in `.claude-plugin/marketplace.json`.
