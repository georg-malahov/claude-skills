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
| [process-video](plugins/process-video/) | Process and share videos: optimize, transcribe, subtitles, and share via tunnel with `/video` command |
| [dev-workflow](plugins/dev-workflow/) | `/orchestrate`, `/create-pr`, `/fix-to-green` — multi-wave ralphex orchestration, gated PR creation, test-first bug fixing |

## Adding New Plugins

Each plugin lives in `plugins/<plugin-name>/` with one of these layouts:

```
plugins/<plugin-name>/
├── .claude-plugin/plugin.json
├── README.md
├── skills/<skill-name>/SKILL.md      # for skills
└── commands/<command-name>.md        # for slash commands
```

A plugin can ship both `skills/` and `commands/`. After adding a new plugin, register it in `.claude-plugin/marketplace.json`.
