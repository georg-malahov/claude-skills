---
name: video
description: >
  Process and share videos. Optimize for web, transcribe audio, add subtitles,
  burn captions, and share via S3 or local tunnel with short unique URLs.
  Triggers on: "process video", "share video", "share latest", "video status",
  "stop sharing", "copy link", "/video".
argument-hint: "[process|share|status|start|stop|copy|remove] [args]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# Video Skill

Process and share videos using ffmpeg, Deepgram Nova 3, and S3/tunnel sharing.

## Prerequisites

- `ffmpeg` and `ffprobe` must be installed
- Python 3 must be available
- `aws` CLI must be available (for S3 uploads)
- Deepgram API key — needed for transcription/subtitles

## Directories

- **Scripts:** `<skill_dir>/scripts/` — all Python scripts and the player.html template
- **Credentials:** `~/.config/video-skill/` — persistent across plugin updates
  - `deepgram_token` — single-line Deepgram API key
  - `s3_credentials` — key=value format (endpoint, bucket, access_key, secret_key)
- **Preferences:** `~/.config/video-skill/preferences.json` — user choices saved across sessions

## Credential Setup

If credentials are missing when needed, ask the user via `AskUserQuestion`:

**Deepgram:** Check `DEEPGRAM_API_KEY` env, then `~/.config/video-skill/deepgram_token` file. If neither exists, ask the user and save to the file.

**S3:** Check env vars (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_ENDPOINT`, `S3_BUCKET`), then `~/.config/video-skill/s3_credentials`. If missing, ask the user for endpoint, bucket, access_key, secret_key and save.

**Important:** Never pass credentials as CLI arguments. Scripts read them from files internally via `--credential-dir ~/.config/video-skill`.

## Preferences

```json
{
  "language": "en",
  "last_folder": "/Users/example/screencasts",
  "share_folder": "/Users/example/screencasts",
  "sharing_method": "s3",
  "optimization": "web-1080p",
  "crf": 23,
  "preset": "medium",
  "audio": "aac-128k",
  "subtitles": "track",
  "subtitle_style": "modern",
  "subtitle_font": "Helvetica Neue",
  "target_language": "ru",
  "download_button": true,
  "passcode": true,
  "developer_analysis": false
}
```

`developer_analysis`: when `true`, the model generates a "Developer Analysis"
section (bugs / UX issues / open questions / prioritized action items) from the
transcript and embeds it in the rendered page. Useful for screencasts that
review a tool, comment on bugs, or give product/UX feedback. Off by default.

**Saving:** After every interactive choice, update `preferences.json`. Always save `last_folder` after every run.
**Loading:** Read at start. Use saved values as "(Recommended)" defaults. In silent mode, use directly.

## Scripts Reference

All scripts are in `<skill_dir>/scripts/`. They accept `--credential-dir` for credentials and print `[PROGRESS]` lines for status tracking.

| Script | Purpose | Key Args |
|--------|---------|----------|
| `process_and_share.py` | Main workflow: optimize + transcribe + render + upload | `<video> --output-dir --share-folder --share s3\|tunnel` |
| `share_existing.py` | Share a pre-processed folder | `<folder> --share-folder --share s3\|tunnel` |
| `upload_s3.py` | Upload folder to S3 | `<folder> --key <key> --credential-dir` |
| `render_page.py` | Generate index.html from template | `--output-dir --template --metadata` |
| `manage_registry.py` | Registry CRUD (add/remove/list/get/migrate) | `<subcommand> --share-folder` |
| `transcribe.py` | Deepgram transcription → SRT + VTT | `<video> --credential-dir [--language]` |
| `burn_subtitles.py` | Burn subtitles into video | `<video> <srt> [--font --fontsize ...]` |
| `share_server.py` | Local HTTP server for tunnel sharing | `<share_root> [--port]` |

## Workflow

### Step 0: Parse Arguments & Detect Mode

**Commands:**
- `/video` → **Interactive mode** (Steps 1-5)
- `/video process <path>` → **Interactive mode** for specific file
- `/video share` → **Silent mode**: process latest + share
- `/video share <path>` → **Silent mode**: process specific file + share
- `/video share <path> "context"` → **Silent mode** with extra context for metadata
- `/video start` → Start sharing server + tunnel
- `/video stop` → Stop sharing
- `/video status` → List shared videos
- `/video copy <key_or_name>` → Copy link + passcode to clipboard
- `/video remove <key_or_name>` → Remove from registry

---

### Sharing Commands (handled directly, no processing)

**Share registry:** `<share_folder>/.share_registry.json` — managed by `manage_registry.py`.

**`start` command:**
1. Read preferences → `share_folder`. If not set, ask.
2. Check `pgrep -f share_server.py`. If running, show status.
3. Start server: `python3 "<scripts>/share_server.py" "<share_folder>" --port 8080 &`
4. Start tunnel: `ssh -p 443 -R0:localhost:<port> -o StrictHostKeyChecking=no a.pinggy.io 2>&1 &`
5. Parse tunnel URL. Show: "Server running at <base_url>"
6. List existing videos with full URLs (`<base_url>/v/<key>`).

**`stop` command:**
`pkill -f share_server.py; pkill -f "ssh.*pinggy"; pkill -f "ngrok http"`

**`status` command:**
1. Run `python3 "<scripts>/manage_registry.py" list --share-folder "<share_folder>"`
2. Check `pgrep -f share_server.py` for tunnel status.
3. Display table: key, title, S3 URL, tunnel URL, passcode, created.

**`copy` command:**
1. Run `python3 "<scripts>/manage_registry.py" get --share-folder "<share_folder>" --key "<query>"`
2. Format: `<title>\n<url>\nPasscode: <code>` → `pbcopy`

**`remove` command:**
Run `python3 "<scripts>/manage_registry.py" remove --share-folder "<share_folder>" --key "<query>"`

---

### Silent Mode (`/video share`)

One confirmation, one script execution, minimal interaction.

**Flow:**
1. Identify video (argument path or newest in `last_folder` / CWD)
2. Create output folder `<share_folder>/<video_name>/`
3. Generate passcode (random 6-digit or saved preference)
4. Show confirmation:
   ```
   Quick share: demo.mov
   → 1080p, CRF 23, AAC 128k
   → Transcribe + subtitles (track)
   → Share via S3 (permanent link)
   → Passcode: 482910
   Proceed?
   ```
   Options: **Proceed (Recommended)** / **Switch to interactive mode**

5. Run the main workflow script. Pass `--developer-analysis` if the saved
   preference (`developer_analysis: true`) is set:
   ```bash
   python3 "<scripts>/process_and_share.py" "<video_path>" \
       --output-dir "<output_folder>" \
       --share-folder "<share_folder>" \
       --credential-dir ~/.config/video-skill \
       --resolution 1080p --crf 23 --preset medium --audio aac-128k \
       --subtitles track \
       --share s3 \
       --passcode "<passcode>" \
       [--developer-analysis] \
       [--context "<user_context>"]
   ```

6. **Monitor stdout for `METADATA_READY:`** — when the script prints this marker:
   a. Read the `TRANSCRIPT_PREVIEW:` and `METADATA_INFO:` that preceded it
   b. Parse `METADATA_INFO:` as JSON to get video_filename, vtt_filename,
      subtitle_lang, and `developer_analysis` (boolean)
   c. Generate title, description, and 4-8 chapters from the transcript preview
   d. **If `developer_analysis` is true**, also generate a structured analysis
      block from the *full* transcript (read the SRT/VTT in the output dir, do
      not rely on the truncated preview). The block must group findings into
      Bugs / UX issues / Open questions / Action items split by priority — same
      structure as the system-review-2026-04-09 page. Write the analysis as raw
      HTML using these CSS classes from the template:
      `severity-high`, `severity-mittel`, `severity-niedrig`, `severity-critical`,
      `task-list`, `priority-section priority-{critical,high,medium,low}`,
      `priority-label`, `summary-box`, `question-list`,
      `<a class="timestamp" data-time="<seconds>">~MM:SS</a>` for clickable jumps.
      Match the page language (RU / DE / EN — same as the transcript).
   e. Write `metadata.json` to the output directory:
      ```json
      {
        "title": "Generated Title",
        "description": "Generated description...",
        "chapters": [{"time": 0, "label": "Intro"}, ...],
        "video_filename": "video_1080p.mp4",
        "subtitle_tracks": [{"src": "video.vtt", "srclang": "en", "label": "English", "default": true}],
        "analysis": {
          "title": "Анализ для разработчика",
          "collapse_label": "Свернуть",
          "expand_label": "Развернуть",
          "html": "<blockquote>...</blockquote><hr><h2>Баги</h2>..."
        }
      }
      ```
      Omit the `analysis` key entirely when `developer_analysis` is false.
   f. The script detects metadata.json and continues automatically.

7. Script finishes. Display result, link is already copied to clipboard.

8. Ask about original file: **Move to output folder (Recommended)** / **Delete** / **Leave in place**

**If already-processed folder (has index.html):** Run `share_existing.py` instead:
```bash
python3 "<scripts>/share_existing.py" "<folder>" \
    --share-folder "<share_folder>" \
    --credential-dir ~/.config/video-skill \
    --share s3 \
    [--passcode "<code>"]
```

---

### Interactive Mode (`/video` or `/video process`)

Full workflow with user choices at each step.

#### Step 1: Language Preference
Ask via `AskUserQuestion`: English (Recommended), German, Russian, or Other.
Save to preferences. All subsequent communication in chosen language.

#### Step 2: Discover Videos
1. Check argument path → `last_folder` from preferences → CWD
2. Find top-level video files (`.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.m4v`)
3. Show 3 newest, let user pick via `AskUserQuestion`
4. Create output subfolder: `<folder>/<video_name>/`
Save `last_folder` to preferences.

#### Step 3: Processing Options
Ask three questions via `AskUserQuestion`:

**Q1: Video optimization** — Save to `preferences.json` → `optimization`
- Optimize for web (1080p) (Recommended)
- Optimize for web (keep resolution)
- Custom settings
- Keep original

**Q2: Subtitles** — Save to `preferences.json` → `subtitles`
- Add subtitles in original language (track only, not burned)
- Add subtitles + burn into video
- Add subtitles in another language (translate)
- No subtitles

**Q3: Developer analysis** — Save to `preferences.json` → `developer_analysis`
- Off (Recommended for general videos)
- Generate developer analysis (bugs / UX / priorities) — for tool reviews & bug reports

When on, the model produces an "Analysis" section embedded in the rendered
page: bugs with severity and timestamps, UX issues, open questions, and
prioritized action items. See the silent-mode section above for the exact
metadata.json shape and CSS classes to use.

#### Step 4: Encoding Settings

If web optimization selected, show default table and ask "Proceed or customize?"

| Setting | Value |
|---------|-------|
| Resolution | 1920×1080 (aspect ratio preserved) |
| Codec | H.264 (libx264) |
| CRF | 23 |
| Preset | medium |
| Audio | AAC 128 kbps |
| Faststart | Yes |

If custom: ask Resolution, CRF, Preset, Audio individually. Save each to preferences.

#### Step 5: Execute Processing

**Build the confirmation summary:**
```
Will process: video.mov (3840×2160, 3:44, 305 MB)
→ 1080p, CRF 23, medium, AAC 128k
→ Transcribe + subtitles as track
→ Developer analysis: yes
→ Share via S3
→ Passcode: 482910
```

The "Developer analysis" line is shown only when the option is enabled.

**User approves once**, then run `process_and_share.py` with the chosen settings.

```bash
python3 "<scripts>/process_and_share.py" "<video_path>" \
    --output-dir "<output_folder>" \
    --share-folder "<share_folder>" \
    --credential-dir ~/.config/video-skill \
    --resolution <resolution> --crf <crf> --preset <preset> --audio <audio> \
    --subtitles <track|burn|none> [--subtitle-lang <code>] \
    --share <s3|tunnel|both|none> \
    --passcode "<passcode>" \
    [--developer-analysis] \
    [--download-button | --no-download-button]
```

**Monitor stdout for `METADATA_READY:`** — same as silent mode step 6.

**Mandatory passcode verification:** when `--passcode` is passed, `render_page.py`
now refuses to write a page that lacks the corresponding `PASSCODE_HASH` and
exits non-zero. If you ever re-render an existing page manually, you MUST
forward the passcode (look it up in `<share_folder>/.share_registry.json` if
you don't have it). Silently producing an unprotected page is no longer
possible from the rendering script.

If subtitles are set to "burn", the script handles it internally after transcription.

If translation was requested (Step 3), the translation itself is done by Claude after receiving the SRT content — this is the one case where more interaction is needed:
1. Script transcribes → generates SRT
2. Claude reads SRT, translates all entries preserving timestamps
3. Claude writes translated SRT to output folder
4. Then runs `burn_subtitles.py` manually if burning was requested

**After the script completes**, show summary table (ffprobe both files) and report results.

## Subtitle Styles (for burn mode)

| Preset | Font | Size | Outline | Shadow | Bold | Color |
|--------|------|------|---------|--------|------|-------|
| Classic | Arial | 18 | 1 | 1 | 1 | White |
| Modern | Helvetica Neue | 18 | 1 | 1 | 1 | White |
| Cinematic | Georgia | 18 | 1 | 0 | 0 | White |
| High Contrast | Arial | 22 | 2 | 2 | 1 | Yellow |

**Important:** Never scale font sizes for higher resolutions. Always downscale to 1080p first.

## Error Handling

- **ffmpeg not installed:** Tell user `brew install ffmpeg`
- **Deepgram 401:** Token expired. Ask for new token via `AskUserQuestion`, save to `~/.config/video-skill/deepgram_token`, re-run
- **S3 credentials missing:** Ask user for endpoint, bucket, access_key, secret_key. Save to `~/.config/video-skill/s3_credentials`
- **No audio track:** Skip transcription. Use filename as title, or ask user for context
- **Script exits non-zero:** Read stderr for error details, report to user
