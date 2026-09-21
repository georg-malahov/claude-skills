---
name: scan
description: >
  Turn a photo of a paper document into a clean A4 PDF that looks scanned on a
  flatbed: even white paper, neutral ink, no desk or shadow around the sheet,
  exact A4 page, small file. Works on JPG/PNG/HEIC and on PDFs that are really
  just a photo. Triggers on: "make a scan", "scan this document", "photo to
  PDF", "clean up this scan", "normalize to A4", "fit to A4", "сделай скан",
  "приведи к А4", "почисти скан", "/scan".
argument-hint: "FILE [FILE ...] [--gray] [--fit auto|edges|content|frame] [--dpi N]"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# Scan — photo of a document → scanner-grade A4 PDF

One script does the whole job: `scripts/a4norm`. **Run it first, look at the
result, tune only if something is actually wrong.** Do not rebuild the pipeline
by hand — every parameter it uses is already exposed as a flag.

## Resolve the script

```bash
A4NORM=""
for c in "${CLAUDE_PLUGIN_ROOT:-/nonexistent}/skills/scan/scripts/a4norm" \
         "$HOME/.claude/skills/scan/scripts/a4norm" \
         "$(command -v a4norm 2>/dev/null)"; do
  [ -x "$c" ] && A4NORM="$c" && break
done
[ -n "$A4NORM" ] || { echo "a4norm not found"; exit 1; }
```

Requires `magick` (ImageMagick 7) and poppler (`pdfinfo`, `pdfimages`,
`pdftoppm`). No ghostscript. On macOS: `brew install imagemagick poppler`.

## Default flow

```bash
"$A4NORM" --preview /path/to/photo.jpg
```

Writes `photo-A4.pdf` next to the input plus `photo-A4-preview.png`, and prints
a per-page report. Then:

1. **Read the preview PNG** with the Read tool. This is not optional — see
   *Verify by looking* below.
2. If it is clean, tell the user the output path and the size. Done.
3. If something is off, match the symptom in the tuning table and rerun with one
   flag. Do not stack flags blindly.

Useful variants:

- `-o "<name>.pdf"` — meaningful filename (single input only). Name the file
  after what the document *is*; ask the user if the subject is unclear.
- `--gray` — grayscale output, ~25% smaller. Colour is the default and keeps a
  blue signature or a red stamp coloured while neutralizing the rest.
- `--dry-run` — analyze and print the report without writing anything. Good for
  explaining what will happen, or for debugging a bad result.
- Several inputs at once: `"$A4NORM" a.jpg b.heic c.pdf` → one PDF per input.
  A multi-page PDF in, a multi-page A4 PDF out.

## What the script does, in order

1. **Rasterize.** For a PDF it extracts the embedded image rather than rendering
   it — rendering applies the ICC profile and flattens the tonal range.
2. **Orient** — EXIF, plus a 90° rotation if the frame is landscape and the
   target is portrait (`--rotate`).
3. **Trim the photographic border.** Finds the sheet edge on each side by a hard
   brightness step whose outer strip does not look like the page, then cuts a
   little further in to drop the edge shadow.
4. **Flat-field.** Divides by a heavily smoothed background estimate, which is
   what turns uneven camera light into even white paper.
5. **Deskew** if the text is off by more than `--deskew-min` (0.4°) and under 5°
   — deliberately *after* the flat-field, because the angle is measured on a
   binarized copy and a dim photo reads as one solid blob, so a real tilt comes
   out as 0.0°. Rotation swings a strip of desk back into frame, so a cut of
   `max_side × sin(angle)` follows on every side that had a detected edge.
6. **Neutralize the ink.** A photo tints black print warm. Everything is pushed
   to neutral grey except pixels that are both high-chroma and dark — real
   coloured ink, any hue — which keep their colour.
7. **Tone** by histogram percentiles (`-contrast-stretch`), not a fixed curve.
8. **Erase leftover haze** — bright *and* featureless areas become paper, so a
   soft shadow or a finger at the edge disappears while anything with structure
   (ink, a faint stamp, a pencil note) survives.
9. **Clean paper to pure white**, protecting a 1 px ring around every glyph.
10. **Fit to A4** (see below) and write JPEG-in-PDF at `--dpi` (300) and
    `--quality` (88, no chroma subsampling — text stays crisp).

## How the A4 scale is chosen (`--fit`, default `auto`)

| Mode | When it applies | How the scale is derived |
|---|---|---|
| `edges` | two **opposite** sheet edges are visible in the frame | that axis spans the whole sheet → exact px-per-mm, no assumption about the layout |
| `content` | no opposite pair, but the ink block spans ≥45% of the frame | the ink block is set to the text width implied by `--margins` (default 30/15/20 mm) |
| `frame` | almost no ink, or nothing else worked | the frame itself is fitted to the page, centred |

`auto` tries them in that order. The report line says which one was used and
with what scale, so a wrong choice is visible without opening the file.

## Tuning table — symptom → one flag

| What you see | Flag |
|---|---|
| a strip of desk / shadow left along an edge | `--trim-shave 2` (percent of the short side shaved inside a detected edge) |
| a real part of the page got cut off | `--no-trim`, or `--trim-step 12` to make edge detection stricter |
| text is too small / too large on the page | `--fit frame`, or `--fit content --margins L,R,T` with the document's real margins |
| a light-grey fill, a pale stamp or a pencil note vanished | `--no-haze`, and if it is still lost `--paper-thr 95` |
| a soft shadow survived in a blank area | `--haze-min 88` |
| a coloured stamp came out grey | `--chroma 5` (more sensitive), or `--chroma-grow 10` to cover stroke edges |
| black print stayed brown / blue-ish | `--chroma 10` (less sensitive), or `--gray` |
| text looks washed out | `--white-clip 4`; if strokes look eaten, `--paper-thr 94` |
| a photo or a dark graphic on the page got bleached | `--close 12 --bg-scale 3` (gentler background estimate), or `--no-flatten-paper` |
| the page came out sideways | `--rotate 90` / `180` / `270`; for a near-square page `--rotate 0` (auto-rotate ignores side differences under `--rotate-tol`, 5%) |
| a handwritten page came out tilted, or the run tilted it | `--no-deskew` — the estimator reads text baselines, and handwriting has none worth trusting |
| the page was shot at an angle and came out as a trapezoid | no flag: there is no perspective correction. Rectify the page quad first (see *Limits*), then run with `--no-trim --fit frame` |
| file too big | `--dpi 200`, `--quality 80`, or `--gray` |

`--dry-run` after a change shows the new decisions without writing a file.

## Verify by looking

**Always read the rendered result before reporting success.** The numbers in the
report can all be plausible while the page is ruined — this is not theoretical,
it is how every bug in this pipeline was actually found:

- a mask composited at the wrong offset erased most of the text; the output was
  still a valid 300 dpi A4 PDF of a few dozen KB;
- a bbox whose offset silently read `+0+0` anchored the frame corner instead of
  the ink, pushing the right edge of every line off the page;
- the first line of text was mistaken for the sheet edge and the whole top
  margin was cut away.

So: `--preview` and Read the PNG, or render the PDF
(`pdftoppm -r 100 -png -singlefile out.pdf check`) and Read that. Check that
nothing is clipped at the right edge, that the top margin survived, and that
signatures and stamps are intact.

## Limits — say these out loud instead of pretending

- **No perspective correction.** A photo taken at an angle keeps its keystone;
  only rotation and small-angle deskew are handled. Ask the user to reshoot
  square-on.
- **Pages are processed independently**, so the scale can differ by a few tenths
  of a percent between pages of one document.
- **The haze filter can eat a genuinely smooth light-grey fill.** `--no-haze`.
- **The `content` fit assumes ordinary margins.** A form printed edge to edge
  needs `--fit frame` or explicit `--margins`.

## Handing back

Report the output path, the file size versus the source, and which fit mode was
used. If anything was tuned away from the defaults, say which flag and why, so
the next run on a similar photo can start there.
