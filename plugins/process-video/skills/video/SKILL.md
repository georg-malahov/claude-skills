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
transcript and embeds it in the rendered page, **and additionally produces
per-block "implementation briefs" as Markdown files** (see "Developer-analysis
block briefs" below). Useful for screencasts that review a tool, comment on
bugs, or give product/UX feedback. Off by default.

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
   d2. **If `developer_analysis` is true, ALSO generate per-block "implementation
      briefs" as Markdown files — this is a mandatory default of the analysis
      step, not optional.** See "Developer-analysis block briefs" below for the
      full contract. In short: partition the full transcript into semantic
      blocks, write one `NN-<slug>-brief.md` per block into the output dir, and
      add a `block_briefs` array to `metadata.json`. The rendered page then shows
      a clickable "Implementation Briefs" box (rendered preview modal + raw
      links); the `.md` files upload automatically with the folder.
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
        },
        "block_briefs": [
          {"num": "01", "name": "Layout & Navigation", "changes": "~10", "file": "01-layout-navigation-brief.md"},
          {"num": "02", "name": "Calendar", "changes": "~9", "file": "02-calendar-brief.md"}
        ]
      }
      ```
      Omit the `analysis` AND `block_briefs` keys entirely when
      `developer_analysis` is false. When it is true, include both. Optional
      localisation keys `block_briefs_title` / `block_briefs_intro` override the
      English box heading/intro to match the page language.
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

## Vertical Video / Instagram Reels

When the source is vertical (e.g. 602×1080 phone footage), **do not pillarbox**. The default 1920×1080 output wraps the video in black bars, which makes burned subtitles span the full 1920px width — far wider than the visible frame.

**Correct approach for vertical content:**
1. Re-encode at native resolution (no pillarboxing):
   ```bash
   ffmpeg -i source.mp4 \
       -vf "scale=W:H:force_original_aspect_ratio=decrease,pad=W:H:(ow-iw)/2:(oh-ih)/2" \
       -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k \
       -movflags +faststart output_vertical.mp4
   ```
2. Burn subtitles into `output_vertical.mp4`, not the pillarboxed version.
3. The resulting file is correct for Instagram Reels upload.

The web player works fine with vertical video — the browser handles aspect ratio natively.

## Subtitle Styles (for burn mode)

### Quick presets (via `burn_subtitles.py`)

| Preset | Font | Size | Outline | Shadow | Bold | Color |
|--------|------|------|---------|--------|------|-------|
| Classic | Arial | 18 | 1 | 1 | 1 | White |
| Modern | Helvetica Neue | 18 | 1 | 1 | 1 | White |
| Cinematic | Georgia | 18 | 1 | 0 | 0 | White |
| High Contrast | Arial | 22 | 2 | 2 | 1 | Yellow |
| Reels (recommended) | Nunito Sans | 11 | 0.5 | 0 | 0 | White |

**Important:** Never scale font sizes for higher resolutions. Always downscale to 1080p first.

### Advanced ASS pipeline (full style control)

`burn_subtitles.py` only exposes `force_style` parameters. For full control (custom fonts, box backgrounds, fine-tuned outline), generate and edit an ASS file directly:

**Step 1 — Convert SRT → ASS:**
```bash
ffmpeg -i input.srt output.ass
```

**Step 2 — Edit the `Style:` line** in `[V4+ Styles]`:
```
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
```

Key fields:
- `BorderStyle=1` — outline only (no box, recommended for Reels)
- `BorderStyle=4` — opaque box background; `Outline` value controls padding size
- `Outline=0.5` — thin 0.5-unit stroke (decimal values work in libass)
- `Bold=0` — use font weight via FontName instead (e.g. "Nunito Sans Light")
- `BackColour=&H80000000` — 50% transparent black box (ASS ABGR, alpha 0x00=opaque)

**Recommended Reels style (ASS Style line):**
```
Style: Default,Nunito Sans,11,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0.5,0,2,5,5,12,1
```
(PlayResX=384, PlayResY=288, video=602×1080 — values are in ASS coordinate space)

**Step 3 — Burn with `ass` filter + `fontsdir`:**
```bash
ASS="output.ass"
ESCAPED=$(echo "$ASS" | sed 's/:/\\:/g')
ffmpeg -i video.mp4 \
    -vf "ass='${ESCAPED}':fontsdir='${HOME}/Library/Fonts'" \
    -c:v libx264 -crf 18 -preset medium -c:a copy \
    output_burned.mp4
```

**Important:** Use `ass=` filter (not `subtitles=:force_style=`) when working with an ASS file directly. The `{\blur}` override tag blurs the text glyphs, not the box border — avoid it with `BorderStyle=4`.

### Google Fonts installation for ffmpeg

libass resolves fonts via fontconfig. Google Fonts must be installed locally first.

**Workflow:**
```bash
# 1. Find TTF download URL via GitHub API
curl -s "https://api.github.com/repos/googlefonts/NunitoSans/contents/fonts/ttf"

# 2. Download the specific weight to ~/Library/Fonts/
curl -sL "<raw_url>" -o ~/Library/Fonts/FontName-Weight.ttf

# 3. Verify it's a real TTF (not an HTML error page)
file ~/Library/Fonts/FontName-Weight.ttf

# 4. Read the exact internal family name (nameID=1) — this is what goes in the ASS Style line
python3 - <<'EOF'
with open('/path/to/font.ttf', 'rb') as f: data = f.read()
import struct
numTables = struct.unpack('>H', data[4:6])[0]
tables = {}
for i in range(numTables):
    rec = data[12+i*16:28+i*16]
    tables[rec[:4].decode('ascii','replace')] = struct.unpack('>II', rec[8:16])
off, ln = tables['name']
nd = data[off:off+ln]
count, strOff = struct.unpack('>HH', nd[2:6])
for i in range(count):
    pid, eid, lid, nid, slen, soff = struct.unpack('>HHHHHH', nd[6+i*12:18+i*12])
    s = nd[strOff+soff:strOff+soff+slen]
    if nid in (1,2,4) and pid == 3:
        try: print(f'nameID={nid}: {s.decode("utf-16-be")}')
        except: pass
EOF

# 5. Use nameID=1 value as FontName in the ASS Style line
# 6. Pass fontsdir= to the ass filter so libass finds the font
```

**Known font name quirks:**
- `Jost-Light.ttf` → internal name is `Jost* Light` (asterisk is part of the name)
- `NunitoSans-Light.ttf` → internal name is `Nunito Sans Light`
- `NunitoSans-Regular.ttf` → internal name is `Nunito Sans`

**Font preview:** A reference HTML page comparing 8 Google Fonts at multiple weights (with subtitle-style rendering) is at `~/projects/screencasts/subtitle-fonts.html`. Open it to pick fonts visually.

### Subtitle segmentation (cleanup after Deepgram)

Deepgram sometimes produces overlapping timestamps and multi-sentence chunks. Clean up manually:
- One sentence per cue maximum
- No overlapping timestamps — end one cue where the next begins
- Merge very short consecutive cues (single words, fragments) into one
- Target 3–5 seconds per cue for Reels; longer is fine for screencasts
- Fix ASR errors (proper nouns, brand names, foreign words) by editing the `.srt` and `.vtt` files directly

## Developer-analysis block briefs

When `developer_analysis` is `true`, the analysis step does **two** things: the
in-page "Developer Analysis" HTML block (above) **and** a set of standalone
**implementation briefs** — one Markdown file per semantic block of the video.
This is a default, not an extra request. The rendered page links each brief in a
clickable "Implementation Briefs" box (rendered-preview modal + raw `.md`
links), and the `.md` files upload automatically with the folder.

### What to produce

1. **Partition the full transcript into semantic blocks** (topics/areas the
   speaker covers — e.g. Layout, Calendar, Communication, …). Order the blocks
   **largest → smallest by number of changes/requirements**. Read the full
   SRT/VTT in the output dir, not the truncated preview.

2. **Write one brief per block** into the output directory, named
   `NN-<slug>-brief.md` (`01-…`, `02-…`, zero-padded, matching the order). Each
   brief contains, in this order:
   - **Title** (`# <Block> — Implementation Block Brief`).
   - **App context** — a few lines so the brief is self-contained, plus an index
     of all blocks (number · name · file) so they cross-link.
   - **Requirements** — concrete, numbered, each with `(~MM:SS)` timestamp(s)
     into the video. Convert the speaker's fuzzy wording into clear requirements;
     flag genuinely open decisions.
   - **Suggested sequencing** — short ordered build plan + cross-block deps.
   - **Verbatim appendix** — the block's raw transcript span(s) with `[MM:SS]`
     markers. **Partition rule: every transcript segment belongs to exactly one
     block, so the union of all appendices reproduces the ENTIRE transcript —
     nothing dropped.** (Verify segment counts add up.)

   Match the page language (RU / DE / EN — same as the transcript). If a later
   meeting/audio revisits the same topics, fold it in as a second "Appendix B"
   and add a short "Meeting update" note per affected brief.

3. **Add a `block_briefs` array to `metadata.json`** (see the metadata example in
   the silent-mode flow). Each item: `{"num","name","changes","file"}` (`num`
   and `changes` optional; `name`+`file` required). `render_page.py` turns this
   into the linked box automatically — do **not** hand-write the box HTML.
   Optional `block_briefs_title` / `block_briefs_intro` localise the heading.

### How it renders & uploads (already wired — no manual steps)

- `render_page.py` reads `block_briefs` and prepends the "Implementation Briefs"
  box to the analysis block. Preview links carry `data-md`; `player.html` fetches
  the `.md`, renders it with a lazy-loaded `marked.js`, and shows it in a modal
  (falls back to raw text if the CDN is blocked). Each row also has a "raw ↗"
  link to the raw file.
- `upload_s3.py` uploads `.md` files (served `text/plain; charset=utf-8`, so raw
  links open inline). Just make sure the briefs are in the output dir before the
  upload step. For an already-shared page, drop new/edited `.md` into the folder
  and re-run the upload (see Partial Update).

## Partial Update (re-render / re-upload only)

To fix metadata, subtitles, or fonts on an already-shared video without re-encoding:

```bash
SKILL_DIR="~/.claude/plugins/cache/georg-malahov-claude-skills/process-video/3.1.0/skills/video"

# 1. Edit metadata.json and/or .srt/.vtt in the output folder

# 2. Re-render the player page
python3 "$SKILL_DIR/scripts/render_page.py" \
    --output-dir "<output_folder>" \
    --template "$SKILL_DIR/scripts/player.html" \
    --metadata "<output_folder>/metadata.json"

# 3. Re-upload (reuses the existing S3 key)
python3 "$SKILL_DIR/scripts/upload_s3.py" \
    "<output_folder>" \
    --key "<existing_key>" \
    --credential-dir ~/.config/video-skill
```

The S3 key is in `<share_folder>/.share_registry.json`.

## Error Handling

- **ffmpeg not installed:** Tell user `brew install ffmpeg`
- **Deepgram 401:** Token expired. Ask for new token via `AskUserQuestion`, save to `~/.config/video-skill/deepgram_token`, re-run
- **S3 credentials missing:** Ask user for endpoint, bucket, access_key, secret_key. Save to `~/.config/video-skill/s3_credentials`
- **No audio track:** Skip transcription. Use filename as title, or ask user for context
- **Script exits non-zero:** Read stderr for error details, report to user
