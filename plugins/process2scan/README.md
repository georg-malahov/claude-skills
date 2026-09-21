# process2scan

A photo of a paper document is not a scan. This plugin turns one into a scan:
even white paper, neutral ink, no desk or shadow around the sheet, an exact A4
page, and a file small enough to email.

```
/scan ~/Downloads/photo.jpg
```

Skill: `scan` · Script: `skills/scan/scripts/a4norm` (standalone, runnable on its
own).

## Install

```
/plugin marketplace add georg-malahov/claude-skills
/plugin install process2scan@georg-malahov-claude-skills
```

Requires ImageMagick 7 and poppler — no ghostscript:

```
brew install imagemagick poppler
```

## Use the script directly

```bash
a4norm photo.jpg                       # -> photo-A4.pdf next to the input
a4norm --preview -o report.pdf scan.pdf
a4norm --gray --dpi 200 *.heic         # one PDF per input
a4norm --dry-run photo.jpg             # analyze and report, write nothing
```

Input: JPG / PNG / HEIC / PDF (including multi-page). Output: A4 PDF, 300 dpi by
default, JPEG-compressed without chroma subsampling.

## What it does

| Step | Why |
|---|---|
| extract, don't render, a PDF's embedded image | rendering applies the ICC profile and flattens the tonal range |
| trim the photographic border | the desk, the shadow line and the sheet's own edge are not part of the document |
| flat-field the illumination | uneven camera light becomes even white paper — this is the step that makes it read as a scan |
| deskew above 0.4°, under 5°, *after* the flat-field | the angle is measured on a binarized copy; on a dim photo the whole sheet falls below the threshold and a real tilt measures as 0.0° |
| neutralize the ink cast, keep coloured ink | a photo tints black print warm; a blue signature or a red stamp must stay coloured |
| tone by histogram percentiles | adapts to the actual file instead of a curve tuned on one photo |
| erase bright featureless haze | a soft shadow or a finger disappears; anything with structure survives |
| clean paper to pure white | with a 1 px guard ring around every glyph |
| fit to A4 | from the real sheet edges when visible, otherwise from the ink block and standard margins |

Every parameter is a flag; `--dry-run` prints what the script decided and why.
See [skills/scan/SKILL.md](skills/scan/SKILL.md) for the symptom → flag table.

## Limits

- No perspective correction — shoot square-on, or the keystone stays.
- Pages of one document are processed independently, so the scale can differ by
  a few tenths of a percent between them.
- The haze filter can erase a genuinely smooth light-grey fill (`--no-haze`).
- The content-based fit assumes ordinary margins; a form printed edge to edge
  needs `--fit frame` or explicit `--margins`.

## Verify the result, always

The report can look perfectly sane while the page is ruined. Use `--preview` and
actually look at the PNG. Every bug found in this pipeline so far — a mask
composited at the wrong offset that erased the text, a bbox offset silently
reading `+0+0` that pushed every line off the right edge, a first line of text
mistaken for the sheet edge — produced a valid-looking A4 PDF and a plausible
report.
