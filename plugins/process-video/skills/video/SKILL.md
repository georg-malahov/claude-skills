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

## Default: lighter video, same resolution

**Always re-encode to a smaller file at the source's own resolution by default.** A
compressed, same-resolution copy is almost always what the user wants — faster
uploads, lighter shares, identical viewing experience. Make this the default in
every flow (silent, interactive, and the Gemini `dev-video` playback encode); only
deviate when the user explicitly says otherwise. Concretely:

- **Default optimization = `--resolution keep`** — re-encode with libx264 + CRF and
  **no scale filter**, so the resolution is unchanged and the file just gets smaller.
  This is the recommended Q1 choice and the silent-mode default.
- **Only downscale** (e.g. to 1080p) when the source is materially larger than 1080p
  (≥1440p / 4K) or the user asks. **Never upscale.**
- **Only skip the re-encode** (use the untouched original / stream-copy) when the user
  **explicitly asks** for the original — e.g. "keep the original", "don't re-encode".
- **Safety check:** after encoding, compare the output size to the source. If it isn't
  meaningfully smaller (rare — e.g. an already-low-bitrate source), raise CRF (26–28)
  or fall back to the original. Screen recordings compress especially well: CRF 24–26
  with `preset slow` routinely cuts 70–80 % while keeping on-screen text crisp.
- **Download buttons:** the page shows a **single "Download Video"** button by default
  (it points at the playback video). Only add a **"Download Original"** button — i.e.
  pass `render_page.py --original-filename <name>` — when you actually upload the
  untouched original into the output folder under that exact name; otherwise the button
  links to a missing file and 404s. The default compress-keep flow keeps no separate
  original, so **do not pass `--original-filename`**.

## Prerequisites

- `ffmpeg` and `ffprobe` must be installed
- Python 3 must be available
- `aws` CLI must be available (for S3 uploads)
- Deepgram API key — for audio transcription/subtitles (default engine)
- OpenRouter API key — for the Gemini analysis engine (`dev-video` / `transcript-cheap` modes). Optional; only needed when those modes are selected.

## Directories

- **Scripts:** `<skill_dir>/scripts/` — all Python scripts and the player.html template
- **Credentials:** `~/.config/video-skill/` — persistent across plugin updates
  - `deepgram_token` — single-line Deepgram API key
  - `openrouter_token` — single-line OpenRouter API key (Gemini analysis engine)
  - `s3_credentials` — key=value format (endpoint, bucket, access_key, secret_key)
- **Preferences:** `~/.config/video-skill/preferences.json` — user choices saved across sessions

## Credential Setup

If credentials are missing when needed, ask the user via `AskUserQuestion`:

**Deepgram:** Check `DEEPGRAM_API_KEY` env, then `~/.config/video-skill/deepgram_token` file. If neither exists, ask the user and save to the file.

**OpenRouter:** Check `OPENROUTER_TOKEN` env, then `~/.config/video-skill/openrouter_token` file. Only needed for `dev-video` / `transcript-cheap` analysis modes. If a Gemini mode is selected and the token is missing, ask the user and save to the file.

**S3:** Check env vars (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_ENDPOINT`, `S3_BUCKET`), then `~/.config/video-skill/s3_credentials`. If missing, ask the user for endpoint, bucket, access_key, secret_key and save.

**Important:** Never pass credentials as CLI arguments. Scripts read them from files internally via `--credential-dir ~/.config/video-skill`.

## Preferences

```json
{
  "language": "en",
  "last_folder": "/Users/example/screencasts",
  "share_folder": "/Users/example/screencasts",
  "sharing_method": "s3",
  "optimization": "compress-keep",
  "crf": 23,
  "preset": "medium",
  "audio": "aac-128k",
  "subtitles": "track",
  "subtitle_style": "modern",
  "subtitle_font": "Helvetica Neue",
  "target_language": "ru",
  "download_button": true,
  "passcode": true,
  "mode": "subtitles"
}
```

`optimization`: how the playback video is encoded. Default **`compress-keep`** =
re-encode lighter at the source resolution (`--resolution keep`). Other values:
`web-1080p` (downscale to 1080p — for ≥1440p/4K sources), `custom`, `keep-original`
(no re-encode — only on explicit user request). See **"Default: lighter video, same
resolution"** above.

`mode`: a single field that decides the transcript/analysis engine. One of four
values (the old `analysis_mode` + `developer_analysis` pair collapsed into this):

| `mode` | Engine | Subtitles | Developer analysis | Use when |
|--------|--------|-----------|--------------------|----------|
| `subtitles` (default) | Deepgram | **precise** | no | normal share, just want captions |
| `dev-audio` | Deepgram | **precise** | yes (from transcript text) | tool/bug feedback, want clean captions too |
| `dev-video` | Gemini video | coarse | **yes + screenshots** | richest tool/UX feedback (reads the screen) |
| `transcript-cheap` | Gemini audio | coarse | no | cheap rough transcript, timing not critical |

Internally: `subtitles`/`dev-audio` run `process_and_share.py` (the latter with
`--developer-analysis`); `dev-video`/`transcript-cheap` run the Gemini engine
(`gemini_analyze.py`). "Developer analysis" = the in-page analysis block **plus**
the Analysis Markdown artifact (see that section). Engine guidance (research
2026-06): keep **Deepgram for precise subtitles**; use **Gemini-video for
analysis**, **Gemini-audio for cheap rough transcripts**. For `dev-video` where
precise captions also matter, additionally run a Deepgram pass for the track.

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
| `partial_update.py` | Re-render + re-upload a shared folder (resolves key from registry, forwards passcode) | `<output_folder> [--key]` |
| `font_name.py` | Print a TTF's internal family name (for ASS `Fontname`) | `<font.ttf>` |
| `transcribe.py` | Deepgram transcription → SRT + VTT | `<video> --credential-dir [--language]` |
| `gemini_analyze.py` | Gemini engine: audio transcript OR video analysis + screenshots | `<video> --mode audio\|video --output-dir --credential-dir [--key]` |
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
   → same resolution · compressed (CRF 23) · AAC 128k
   → Transcribe + subtitles (track)
   → Share via S3 (permanent link)
   → Passcode: 482910
   Proceed?
   ```
   Options: **Proceed (Recommended)** / **Switch to interactive mode**

   **If `mode` is `dev-video` or `transcript-cheap`**, do not run
   `process_and_share.py` — follow the "Gemini analysis engine" section instead
   (silently, using saved preferences), then still upload + register the share.

5. Run the main workflow script. Pass `--developer-analysis` when `mode` is
   `dev-audio`:
   ```bash
   python3 "<scripts>/process_and_share.py" "<video_path>" \
       --output-dir "<output_folder>" \
       --share-folder "<share_folder>" \
       --credential-dir ~/.config/video-skill \
       --resolution keep --crf 23 --preset medium --audio aac-128k \
       --subtitles track \
       --share s3 \
       --passcode "<passcode>" \
       [--developer-analysis] \
       [--context "<user_context>"]
   ```
   Default `--resolution keep` (compress, same resolution). Use `--resolution 1080p`
   only if the source is ≥1440p/4K, or `keep-original` handling if the user explicitly
   wants the untouched file.

6. **Monitor stdout for `METADATA_READY:`** — when the script prints this marker:
   a. Read the `TRANSCRIPT_PREVIEW:` and `METADATA_INFO:` that preceded it.
   b. Generate title, description, and 4-8 chapters from the transcript preview.
   c. **If `mode` is `dev-audio`** (developer analysis on): build the analysis
      block **and** the Analysis Markdown from the *full* transcript (read the
      SRT/VTT in the output dir, not the truncated preview). See the
      **"metadata.json reference"** and **"Analysis Markdown"** sections for the
      exact shape and contract. Match the page language (RU / DE / EN).
   d. Write `metadata.json` to the output dir per the **metadata.json reference**.
   e. The script detects metadata.json and continues automatically.

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
- **Compress, keep resolution** — lighter file, same resolution (Recommended) → `compress-keep`
- Downscale to 1080p — only worth it for ≥1440p/4K sources → `web-1080p`
- Custom settings → `custom`
- Keep original — no re-encode, only on explicit request → `keep-original`

(Default to **Compress, keep resolution** per **"Default: lighter video, same
resolution"**. Pick "Keep original" only when the user explicitly asks for the
untouched file.)

**Q2: Subtitles** — Save to `preferences.json` → `subtitles`
- Add subtitles in original language (track only, not burned)
- Add subtitles + burn into video
- Add subtitles in another language (translate)
- No subtitles

**Q3: Analysis mode** — Save the chosen value to `preferences.json` → `mode`.
Four options (map 1:1 to the `mode` enum in Preferences):
- **Subtitles only (Deepgram)** (Recommended for general videos) → `subtitles`
- **Developer analysis from audio (Deepgram)** — bugs/UX/priorities, precise subtitles → `dev-audio`
- **Developer analysis from VIDEO (Gemini)** — reads the screen, embeds screenshots (Recommended for tool/UX feedback) → `dev-video`
- **Cheap audio transcript (Gemini)** — subtitles only, approximate timing → `transcript-cheap`

`subtitles`/`dev-audio` use the standard `process_and_share.py` flow;
`dev-video`/`transcript-cheap` use the **Gemini analysis engine**
(`gemini_analyze.py`). The choice is saved and reused as the default next run.

#### Step 4: Encoding Settings

If web optimization selected, show default table and ask "Proceed or customize?"

| Setting | Value |
|---------|-------|
| Resolution | Source resolution, unchanged (`keep`) — downscale to 1080p only for ≥1440p/4K |
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
→ downscaled to 1080p (source is 4K), CRF 23, medium, AAC 128k
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

Map `optimization` → `--resolution`: `compress-keep` → `keep` (default), `web-1080p`
→ `1080p`, `custom` → the chosen value. For `keep-original`, skip `process_and_share.py`'s
re-encode entirely and share the source as-is (only when the user explicitly asked).

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

## Gemini analysis engine (`dev-video` / `transcript-cheap`)

Used when `mode` is `dev-video` or `transcript-cheap`. Driven by
`gemini_analyze.py`, which reads `openrouter_token` + `s3_credentials` from
`--credential-dir`. It prints `[PROGRESS]`/`[COST]` lines and (video mode) a final
`RESULT_JSON:` line. **Never pass tokens as CLI args** — the script reads files.

### `transcript-cheap` — cheap transcript → subtitles
```bash
python3 "<scripts>/gemini_analyze.py" "<video>" --mode audio \
    --output-dir "<output_folder>" --credential-dir ~/.config/video-skill
```
Extracts a compact mp3, sends it inline to Gemini, writes `video.srt` + `video.vtt`.
Then encode the playback video, build `metadata.json` (with `subtitle_tracks`, no
analysis), render, and upload like a normal share. **Timing is approximate** — fine
for rough captions, not tight ones.

### `dev-video` — full visual analysis with screenshots
This path does **not** use `process_and_share.py`. Steps:

1. **Encode the playback video** for the page — **re-encode lighter at the source's
   own resolution** (no scaling), e.g.
   `ffmpeg -i <video> -c:v libx264 -crf 24 -preset slow -c:a aac -b:a 128k -movflags +faststart "<out>/video.mp4"`.
   Reference this file in `metadata.json` → `video_filename`. Downscale only if the
   source width > 1920 (add `-vf scale=1920:-2`); never upscale. Screen recordings
   shrink dramatically at CRF 24–26 + `preset slow` with text still legible — verify
   the output is smaller than the source, else raise CRF.
   Pick/confirm the S3 `<key>` for this share now (the engine uploads a temp proxy under it).

2. **Run the engine** (encodes a ≤15 MiB fps=1 proxy, uploads it, calls Gemini once
   for analysis **+** transcript, extracts a `shot-<sec>.jpg` frame at every finding
   and visual-detail timestamp, writes `video.srt`/`video.vtt`, deletes the temp proxy):
   ```bash
   python3 "<scripts>/gemini_analyze.py" "<video>" --mode video \
       --output-dir "<output_folder>" --credential-dir ~/.config/video-skill \
       --key "<share_key>"
   ```
   Parse the `RESULT_JSON:` line → `{analysis, screenshots, transcript_file, cost}`.
   `analysis` has: `title, description, summary, language, chapters[], findings[]`
   (`type` bug|ux|idea, `severity`, `time`, `ui`, `verbatim`), `visual_details[]`,
   `questions[]`, `tasks[]`, `transcript`.

3. **Build the Analysis Markdown** (`dev-analysis.md`) in the output dir, embedding
   screenshots via **absolute public URLs** — see the **"Analysis Markdown"** section.

4. **Write `metadata.json`** per the **"metadata.json reference"** section:
   title/description/chapters from `analysis`; `subtitle_tracks` → `video.vtt`;
   `analysis.html` from the findings; and a `block_briefs` entry pointing at
   `dev-analysis.md`. In the analysis HTML, **embed each screenshot** with this
   figure pattern so the image opens the lightbox and the caption seeks the player:
   ```html
   <figure>
     <img class="zoomable" src="shot-540.jpg" alt="<caption>" loading="lazy"
          style="display:block;width:360px;max-width:100%;border:1px solid #2a2a2a;border-radius:6px">
     <figcaption style="font-size:0.75rem;color:#888">
       <a class="timestamp" data-time="540">▶ 09:00</a> · <caption></figcaption>
   </figure>
   ```

5. **Render + upload.** Render with
   `render_page.py --output-dir <out> --template <player.html> --metadata <metadata.json> --download-button`
   (add `--passcode` only if the share has one). **Do NOT pass `--original-filename`**
   here — the dev-video flow uploads only the compressed playback video, so a
   "Download Original" button would 404. Pass it *only* when you deliberately also place
   the untouched original in `<out>` under that exact name. Then `upload_s3.py` (reusing
   `<key>`; uploads `.jpg`/`.png`/`.md` automatically) and register with
   `manage_registry.py`.

**Verify visual claims before trusting them:** Gemini occasionally misreads on-screen
text (e.g. product name, button labels). Open a few `shot-*.jpg` and correct the
`ui`/`verbatim`/labels in `dev-analysis.md` + the analysis HTML.

### Player features (automatic — no manual steps)
`player.html` already provides: the markdown preview modal + lazy `marked.js`, the
**⧉ Copy** button (copies raw markdown incl. image URLs), the image **lightbox**
(click any analysis/preview screenshot → full-screen; click again or Esc to close),
and chapter/timestamp clicks that smooth-scroll the player into view. You only
supply `block_briefs` + the figure markup above.

### Cost & engine notes (research 2026-06)
- dev-video ≈ **$0.03** / 14 min; transcript-cheap ≈ **$0.015** / 14 min;
  Deepgram Nova-3 ≈ $0.0043/min (~$0.06 / 14 min) but gives precise word timing.
- Gemini's combined call returns a **coarse** transcript (few markers) and has a
  known timestamp-drift issue. For tight captions, prefer Deepgram. Gemini wins on
  cheap rough transcripts and on visual analysis audio cannot capture.

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
python3 "<scripts>/font_name.py" ~/Library/Fonts/FontName-Weight.ttf
#   → family (nameID=1): <use this as Fontname>

# 5. Use the family name as FontName in the ASS Style line
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

## metadata.json reference

The single source of truth for the rendered-page metadata. Both the Deepgram flow
(silent/interactive) and the Gemini engine write this same file; only the deltas
noted below differ.

```json
{
  "title": "Generated Title",
  "description": "Generated description...",
  "chapters": [{"time": 0, "label": "Intro"}, ...],
  "video_filename": "video_1080p.mp4",
  "subtitle_tracks": [{"src": "video.vtt", "srclang": "de", "label": "Deutsch", "default": false}],

  "analysis": {                          // developer-analysis modes only
    "title": "Entwickler-Analyse",       // localise per page language
    "collapse_label": "Einklappen",
    "expand_label": "Ausklappen",
    "html": "<blockquote>...</blockquote><hr><h2>Bugs</h2>..."
  },
  "block_briefs": [                       // developer-analysis modes only
    {"num": "01", "name": "Layout & Navigation", "changes": "~10", "file": "01-layout-navigation-brief.md"}
  ],
  "block_briefs_title": "…",             // optional, localise the box heading
  "block_briefs_intro": "…"              // optional, localise the box intro
}
```

- **`analysis.html`** — raw HTML using these template CSS classes: `severity-high`,
  `severity-mittel`, `severity-niedrig`, `severity-critical`, `task-list`,
  `priority-section priority-{critical,high,medium,low}`, `priority-label`,
  `summary-box`, `question-list`, and `<a class="timestamp" data-time="<seconds>">~MM:SS</a>`
  for clickable jumps. `dev-video` additionally embeds `<figure>` screenshots (see
  the engine section's figure pattern).
- **`block_briefs`** — each item `{"num","name","changes","file"}` (`num`/`changes`
  optional; `name`+`file` required). `render_page.py` turns this into the clickable
  preview box automatically — **never hand-write that box HTML**.
- **Omit `analysis` + `block_briefs`** entirely for `subtitles` / `transcript-cheap`
  modes. Include both for `dev-audio` / `dev-video`.

## Analysis Markdown

When `mode` is `dev-audio` or `dev-video`, the analysis step produces — besides the
in-page analysis HTML — **standalone Markdown** registered via `block_briefs` and
shown in the page's preview modal (rendered + a ⧉ Copy button + raw `.md` link).
`render_page.py` builds the box; `upload_s3.py` uploads the `.md` (served
`text/plain`) and any screenshots automatically.

**One file or many — same artifact, pick by scope:**
- **One file** (`dev-analysis.md`) — default for a focused video (one tool/area).
  `dev-video` always uses this, with embedded screenshots.
- **Per-block files** (`NN-<slug>-brief.md`, `01-…` zero-padded, ordered
  largest→smallest by # of changes) — when the video covers **many distinct areas**
  and you want each implementable in its own session. Each brief carries an index of
  all blocks so they cross-link.

**Each file contains, in order:**
1. **Title** + a context block (product, source, video-page URL) — self-contained.
2. **Context for agents** — app model, navigation, key entities.
3. **Summary** + a chapters table.
4. **Findings** (Bugs / UX / Ideas), each with: an embedded screenshot when one
   exists (**absolute public URL** `https://<bucket>.<endpoint>/sharing-videos/<key>/shot-<sec>.jpg`
   so downstream LLMs can fetch it), a plain observation, severity, and a
   **verbatim quote** (`**Verbatim [MM:SS]:** "…"`).
5. **Open questions** + a prioritized task checklist.
6. **Appendix — full verbatim transcript** with `[MM:SS]` markers. For per-block
   files the **partition rule** applies: every transcript segment belongs to exactly
   one block, so the union of all appendices reproduces the ENTIRE transcript —
   nothing dropped (verify the segment counts add up).

Match the page language (DE/EN/RU). If a later meeting/audio revisits the topics,
fold it in as "Appendix B" + a short "Meeting update" note per affected file.

## Partial Update (re-render / re-upload only)

To fix metadata, subtitles, screenshots, or fonts on an already-shared video
without re-encoding: edit `metadata.json` / `.srt` / `.vtt` / `.md` in the output
folder, then run the one-step wrapper — it resolves the S3 key from the registry
and forwards the registered passcode automatically:

```bash
python3 "<scripts>/partial_update.py" "<output_folder>" \
    --credential-dir ~/.config/video-skill
# pass --key <key> if the folder isn't in the registry
```

`partial_update.py` just composes `render_page.py` + `upload_s3.py`; run them
directly only if you need to override something. The S3 key is in
`<share_folder>/.share_registry.json`.

## Error Handling

- **ffmpeg not installed:** Tell user `brew install ffmpeg`
- **Deepgram 401:** Token expired. Ask for new token via `AskUserQuestion`, save to `~/.config/video-skill/deepgram_token`, re-run
- **OpenRouter 401/insufficient credits:** Ask for a new key, save to `~/.config/video-skill/openrouter_token`, re-run. (`gemini_analyze.py` only.)
- **Gemini URL fetch "File content exceeded the size limit":** the proxy is over ~15 MiB. `gemini_analyze.py` escalates compression automatically; if it still fails, the source is unusually long — lower fps or split the video.
- **Gemini returned no JSON (video mode):** raw saved to `<output>/_analysis_raw.txt`; inspect and retry, or fall back to an audio mode.
- **S3 credentials missing:** Ask user for endpoint, bucket, access_key, secret_key. Save to `~/.config/video-skill/s3_credentials`
- **No audio track:** Skip transcription. Use filename as title, or ask user for context
- **Script exits non-zero:** Read stderr for error details, report to user
