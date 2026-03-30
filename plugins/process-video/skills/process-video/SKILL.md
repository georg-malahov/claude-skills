---
name: process-video
description: >
  Use this skill when the user wants to process videos: optimize/compress for web,
  downscale resolution, add subtitles, transcribe audio, translate subtitles, or
  burn captions into video. Triggers on: "process video", "optimize video", "compress video",
  "subtitles", "transcribe", "add captions", "SRT", "video for web", "/process-video".
argument-hint: "[folder_path]"
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - AskUserQuestion
---

# Process Video Skill

Process videos with optimization, subtitles, transcription, and translation using ffmpeg and Deepgram Nova 3.

## Prerequisites

- `ffmpeg` and `ffprobe` must be installed
- Python 3 must be available
- Deepgram API key — needed only for subtitle features. Resolved in this order:
  1. Environment variable `DEEPGRAM_API_KEY` (best option — user sets in shell profile)
  2. Config file at `<skill_dir>/deepgram_token` (single line, token only)
  3. If neither exists, or if the token is expired/invalid (Deepgram returns 401), ask the user to provide a temporary token via `AskUserQuestion`. Save it to `<skill_dir>/deepgram_token` for the rest of the session. Remind the user that they are responsible for providing a restricted, temporary token.

To set the token permanently, the user can add to their shell profile (`~/.zshrc` or `~/.bashrc`):
```bash
export DEEPGRAM_API_KEY="your-token-here"
```

## Workflow

Follow these steps in order. Use `AskUserQuestion` for interactive selections.

### Step 1: Language Preference

Ask the user which language they prefer for all communication during this session using `AskUserQuestion`:

- **English** (Recommended)
- **German (Deutsch)**
- **Russian (Русский)**

The user can also type a custom language via "Other". From this point forward, **all questions, explanations, previews, and the final summary must be in the chosen language**. SRT subtitle content language is separate — this only controls the UI/conversation language.

If at any point during the conversation the user switches language or asks to communicate in a different language, simply switch — no need to re-ask.

### Step 2: Discover Videos

Determine the target folder:
- If the user provided a folder path as argument, use that
- Otherwise, use the current working directory

Find video files **only in the top level** of that folder (extensions: `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.m4v`).
**Exclude** any files inside subdirectories — these may be previously generated outputs.
Sort by modification time (newest first) and present the **3 newest** videos to the user.

Use `AskUserQuestion` with the video filenames as options. Let the user pick which video to process.

### Step 2a: Create Output Folder

After the user selects a video, create a subfolder named after the video (without extension) in the same directory:

```
<folder>/<video_name>/
```

For example, selecting `Thomas Roth.mp4` creates `Thomas Roth/`. All generated files — optimized videos, SRT files, subtitled videos — go into this folder. This keeps the source folder clean and prevents generated files from appearing in future video discovery.

If the folder already exists (e.g., re-running on the same video), reuse it. Inform the user that existing files may be overwritten.

### Step 3: What to Do

Ask the user what they want using `AskUserQuestion`. Combine into a single question batch when possible.

**Question 1: Video optimization**
- **Optimize for web (1080p)** (Recommended) — Downscale to 1080p, smaller file, fast streaming
- **Optimize for web (keep resolution)** — Keep original resolution but compress for smaller file size
- **Custom settings** — Choose resolution, quality, speed, and audio settings manually
- **Keep original** — No re-encoding of the base video (subtitles, if any, will still require re-encoding)

**Question 2: Subtitles** (optional feature)
- **Add subtitles in original language** — Transcribe audio and burn subtitles in the detected language
- **Add subtitles in another language** — Transcribe, translate, and burn subtitles in a target language
- **Add subtitles in both (separate videos)** — Create two output videos: one with original subtitles, one with translated subtitles
- **No subtitles** — Skip subtitle processing entirely

### Step 4: Encoding Settings

**Important:** All setting names, descriptions, and explanations in this step must be presented **in the user's chosen language** from Step 1. The table below is the English reference — translate it when presenting to the user.

**If the user chose "Optimize for web (1080p)" or "Optimize for web (keep resolution)"**, use these defaults and briefly tell the user what will be applied:

| Setting | Value | What it means (translate to user's language) |
|---------|-------|----------------------------------------------|
| Resolution | 1920×1080 (or original) | How many pixels — 1080p is the standard for web/mobile |
| Codec | H.264 (libx264) | The most compatible video format — plays everywhere |
| CRF | 23 | Quality level: lower = bigger & sharper, higher = smaller & softer. 23 is the sweet spot for web |
| Preset | medium | Encoding speed vs compression: slower = smaller file but takes longer to process |
| Audio | AAC 128 kbps | Standard web audio quality — clear speech, small size |
| Faststart | Yes | Moves metadata to the front so the video starts playing immediately in browsers |

Then ask: **"These are the recommended web settings. Want to adjust anything, or proceed?"**
- **Proceed with these settings** (Recommended)
- **Let me customize**

**If the user chose "Custom settings"** or wants to customize, present each setting as a separate `AskUserQuestion` with clear explanations:

**Resolution:**
- **1080p (1920×1080)** (Recommended) — Standard HD, great for web/mobile, major size savings from 4K
- **720p (1280×720)** — Compact, good for bandwidth-constrained use, mobile-friendly
- **Keep original** — No scaling, preserves every pixel
- Other (user types custom, e.g., 2560×1440)

**Quality (CRF):**
- **18 — High quality** — Visually near-lossless. Larger files. Best for archival or when you'll edit further.
- **23 — Balanced** (Recommended) — Excellent quality at reasonable size. The industry default for web delivery.
- **28 — Compact** — Noticeable softness on close inspection but very small files. Good for previews or mobile.
- Other (user types a number 0–51; explain: 0 = lossless, 51 = worst)

**Encoding speed (preset):**
- **fast** — Quick processing, slightly larger output file
- **medium** (Recommended) — Good balance between speed and compression
- **slow** — Smaller output file, takes noticeably longer to process
- **veryslow** — Maximum compression, significantly longer. Best when file size matters more than time.

Explain: "Slower presets try harder to compress. A 'slow' encode might be 10–20% smaller than 'fast' at the same quality, but take 3–4× longer."

**Audio:**
- **AAC 128k** (Recommended) — Standard quality for speech and general content
- **AAC 192k** — Higher quality, good for music-heavy content
- **Copy (no re-encode)** — Keep original audio as-is, fastest, no quality loss
- Other (user types custom, e.g., "opus 96k")

After all settings are confirmed, show a one-line summary like:
> **Settings:** 1080p, H.264 CRF 23, medium preset, AAC 128k, faststart

### Step 5: Optimize Video (if requested)

If the user selected any optimization option, build the ffmpeg command from the chosen settings:

```bash
ffmpeg -y -i "<video_path>" \
    [-vf "scale=<width>:<height>"] \
    -c:v libx264 -crf <crf> -preset <preset> \
    -movflags +faststart \
    -c:a <audio_codec> [-b:a <audio_bitrate>] \
    "<output_video>"
```

- Omit `-vf scale` if "Keep original" resolution was chosen
- Use `-c:a copy` if the user chose "Copy" for audio
- Always include `-movflags +faststart` for web optimization
- **Output goes into the subfolder** from Step 2a (e.g., `Thomas Roth/Thomas Roth_1080p.mp4`)

Use the optimized video as the base for any subsequent subtitle burning.

If the user chose "Keep original" and subtitles are needed, use the original file as the base for burning.

### Step 5a: Follow-up Questions (if subtitles enabled)

**If translation was selected, ask: Target language**
- Common options: English, German, Russian (let user type custom via Other)

**Subtitle style** — show style presets with previews:

- **Classic** — White text, black outline, clean and readable
  Preview: `White, Arial 18, outline 1px, shadow 1`
- **Modern** (Recommended) — Semi-bold, subtle shadow, contemporary
  Preview: `White, Helvetica Neue 18, outline 1px, shadow 1`
- **Cinematic** — Elegant serif, thin outline, film-like
  Preview: `White, Georgia 18, outline 1px, no shadow`
- **High Contrast** — Bold yellow on black, maximum readability
  Preview: `Yellow, Arial 22, outline 2px, shadow 2`

**Font selection**: Run `fc-list : family | sort -u` and suggest 4 popular options:
- The font from the chosen preset
- A sans-serif alternative
- A serif alternative
- A monospace alternative

Let the user pick or type a custom font name.

### Step 6: Transcribe with Deepgram (if subtitles enabled)

**Token resolution — check before running the script:**

1. Check if `DEEPGRAM_API_KEY` environment variable is set (run `echo $DEEPGRAM_API_KEY`)
2. If not, check if token file exists at `<skill_dir>/deepgram_token` (read it)
3. If neither exists, ask the user:

Use `AskUserQuestion`:
> "A Deepgram API key is needed for transcription. How would you like to provide it?"
- **Enter token now** — User types the token. Save it to `<skill_dir>/deepgram_token` for future reuse.
- **I've set DEEPGRAM_API_KEY in my environment** — User will set it themselves, then re-run.

When the user provides a token, write it to `<skill_dir>/deepgram_token` using the Write tool (single line, token only). This file is local to the skill inside the project — not global, not shared.

**Run the transcription script** (output goes into the output folder from Step 2a):

```bash
python3 "<skill_scripts_dir>/transcribe.py" "<original_video_path>" [--language <code>] [--token <key>] --output "<output_folder>/<video_name>.srt"
```

Where `<skill_scripts_dir>` is the absolute path to this skill's `scripts/` directory.

- If the user specified a source language, pass `--language <code>`
- Otherwise, let Deepgram auto-detect
- Always transcribe from the **original** video (not the optimized one) for best audio quality

**If the script fails with "INVALID_AUTH" or 401:**
The saved token is likely expired. Tell the user clearly:
> "The Deepgram token is expired or invalid. Please provide a new temporary token."

Ask for a new token via `AskUserQuestion`, overwrite `<skill_dir>/deepgram_token` with the new value, and re-run the script. This loop continues until transcription succeeds or the user cancels.

After transcription, read the generated SRT file and show a preview (first 10 entries) to the user.

### Step 7: Review Original Subtitles

After showing the preview, ask the user how they want to proceed using `AskUserQuestion`:

**Question: Review the original transcript?**
- **Looks good, continue** (Recommended) — Proceed to translation (if any) or burning
- **I'll fix it here in chat** — The user will describe corrections (e.g., "entry 6 should say X", "remove entry 3"). Apply each correction using the Edit tool on the SRT file. After applying, show the updated entries and ask again (loop back to this question).
- **I'll edit the file externally** — Tell the user the full path to the SRT file and ask them to edit it in their preferred text editor. Then ask them to confirm when done (use `AskUserQuestion` with "I'm done editing" / "Cancel"). After confirmation, re-read the file and show the updated preview.

**Key behaviors:**
- This review step is a loop: after any correction, re-show the affected entries and ask the same question again. Only proceed when the user selects "Looks good, continue".
- When the user describes corrections in chat, apply them precisely — fix the text but never alter timestamps unless explicitly asked.
- If the user says something like "looks fine" or "let's go" at any point, treat it as "Looks good, continue".

### Step 8: Translate (if requested)

If translation was requested:
1. Read the full (possibly edited) SRT file
2. Translate ALL subtitle entries to the target language while preserving:
   - SRT numbering
   - Timestamps (exactly as-is)
   - Line breaks within entries
3. Write the translated SRT to `<video_name>_<target_lang>.srt`
4. Show a preview of the first 10 translated entries

**Translation guidelines:**
- Maintain natural sentence flow in the target language
- Keep translations concise (subtitles should be readable quickly)
- Preserve any speaker labels or formatting

### Step 9: Review Translated Subtitles (if translation was done)

Same review loop as Step 6, but for the translated SRT file:

**Question: Review the translated subtitles?**
- **Looks good, continue** (Recommended) — Proceed to burning
- **I'll fix it here in chat** — Apply corrections via Edit tool, re-show, loop
- **I'll edit the file externally** — Show path, wait for confirmation, re-read

Same loop behavior: only proceed to burning when the user confirms.

### Step 10: Burn Subtitles into Video (if subtitles enabled)

Map the style preset to burn_subtitles.py arguments:

| Preset | --font | --fontsize | --outline | --shadow | --bold | --fontcolor | --outlinecolor |
|--------|--------|-----------|-----------|----------|--------|-------------|----------------|
| Classic | Arial | 18 | 1 | 1 | 1 | &H00FFFFFF | &H00000000 |
| Modern | Helvetica Neue | 18 | 1 | 1 | 1 | &H00FFFFFF | &H40000000 |
| Cinematic | Georgia | 18 | 1 | 0 | 0 | &H00FFFFFF | &H00000000 |
| High Contrast | Arial | 22 | 2 | 2 | 1 | &H0000FFFF | &H00000000 |

**Important:** Do NOT scale font sizes for higher resolutions. ASS/libass font sizes are resolution-independent. Always downscale to 1080p first if the source is larger.

Run the burn script:

```bash
python3 "<skill_scripts_dir>/burn_subtitles.py" "<video_path>" "<srt_path>" \
    --output "<output_video>" \
    --font "<font>" --fontsize <size> --outline <outline> --shadow <shadow> \
    --bold <bold> --fontcolor "<color>" --outlinecolor "<outline_color>" \
    --margin-v <margin> --crf 23
```

**Two separate videos (both languages):** When the user chose "both (separate videos)", burn each SRT into its own output video independently. Run them in parallel if possible. **All output files go into the subfolder** from Step 2a, named `<video_name>_<lang>_subtitled.<ext>`.

The script reports progress every 10 seconds with ETA. Let the output stream to the user.

### Step 11: Summary

Use `ffprobe` to gather full metadata for both the original and each output video. Present a comparison table like this:

```
## Processing Complete

### Source vs Output

| Property          | Original              | Output (DE subs)      | Output (RU subs)      |
|-------------------|-----------------------|-----------------------|-----------------------|
| File              | Thomas Roth.mp4       | Thomas Roth_de.mp4    | Thomas Roth_ru.mp4    |
| Resolution        | 3840×2160             | 1920×1080             | 1920×1080             |
| Codec             | H.264 High            | H.264 High            | H.264 High            |
| Frame rate        | 25 fps                | 25 fps                | 25 fps                |
| Bitrate (video)   | 10.8 Mbps             | 2.8 Mbps              | 2.8 Mbps              |
| Audio             | AAC 48kHz             | AAC 48kHz 128k        | AAC 48kHz 128k        |
| Duration          | 3:44                  | 3:44                  | 3:44                  |
| File size         | 305.7 MB              | 80.4 MB               | 80.4 MB               |
| Size reduction    | —                     | -73.7%                | -73.7%                |
| Subtitles         | None                  | German (57 entries)   | Russian (57 entries)  |
| Web optimized     | No                    | Yes (faststart)       | Yes (faststart)       |
```

Adjust the number of output columns based on how many videos were generated (could be 1, 2, or just an optimized version without subtitles).

**Additional details to report below the table:**
- SRT file path(s) with entry count
- Detected spoken language
- Subtitle style used (font, size, outline, shadow)
- Total processing time

Gather the data by running `ffprobe -v quiet -print_format json -show_format -show_streams` on each file and extracting: width, height, codec_name, r_frame_rate, bit_rate (from video stream), codec_name + sample_rate + bit_rate (from audio stream), duration, and size from format.

## Error Handling

- If ffmpeg is not installed, tell the user to install it (`brew install ffmpeg` on macOS)
- If Deepgram returns an error, show the error message and suggest checking the API key
- If the video has no audio track, inform the user that subtitles cannot be generated
- If font is not available, fall back to Arial

## Notes

- Audio is extracted as 16kHz mono WAV before sending to Deepgram (much smaller than raw video)
- CRF 23 is the optimal balance between quality and size for web delivery
- The `-progress pipe:1` flag enables real-time progress tracking from ffmpeg
- The `+faststart` flag moves metadata to the start of the file for web streaming
