# a4norm

A photo of a paper document is not a scan. This plugin turns one into a scan:
even white paper, neutral ink, no desk or shadow around the sheet, an exact A4
page, and a file small enough to email.

```
/a4norm ~/Downloads/photo.jpg
/a4norm page1.HEIC page2.HEIC page3.HEIC   # one multi-page PDF
```

Skill: `a4norm` · Programs: `skills/a4norm/scripts/a4norm` (CLI) and
`a4norm-serve` (HTTP), both standalone.

The tool also lives on its own at [github.com/georg-malahov/a4norm](https://github.com/georg-malahov/a4norm)
and as a public image `ghcr.io/georg-malahov/a4norm`. The builds here are
copies of its main — replace them together when it moves.

**See it working without installing anything:** [@a4norm_bot](https://t.me/a4norm_bot)
on Telegram runs that same image behind a chat window — send a photo, or a whole
album, and the A4 PDF comes back.

## Install

```
/plugin marketplace add georg-malahov/claude-skills
/plugin install a4norm@georg-malahov-claude-skills
```

## Dependencies

None for JPEG, PNG and WebP. `scripts/a4norm` starts a native build of the
Rust a4norm for this machine, from `scripts/bin/`:

| platform | build |
|---|---|
| macOS, Apple silicon | `a4norm-darwin-arm64` |
| macOS, Intel | `a4norm-darwin-x86_64` |
| Linux x86_64, any distribution | `a4norm-linux-x86_64` (static) |
| Linux arm64, any distribution | `a4norm-linux-aarch64` (static) |

Each is about 2.5 MB and does everything itself — decoding, every pixel
operation, the PDF. No ImageMagick, no Python, no ghostscript. All four give the
same bytes for the same photo.

Two inputs still call out to a tool:

| input | tool |
|---|---|
| HEIC | `magick` (with libheif) or `heif-convert` |
| PDF | poppler (`pdfinfo`, `pdfimages`, `pdftoppm`) |

```
brew install imagemagick poppler      # macOS, for HEIC and PDF input
```

On any other platform: `cargo install --git https://github.com/georg-malahov/a4norm a4norm-rs --features par`,
or the container below.

## Docker

The image and its Dockerfile live in the [a4norm
repository](https://github.com/georg-malahov/a4norm) — one source, no vendored
copy to drift:

```
docker run --rm -v "$PWD:/work" ghcr.io/georg-malahov/a4norm:latest \
  -o /work/doc.pdf /work/p1.HEIC /work/p2.HEIC

docker run --rm -p 8080:8080 ghcr.io/georg-malahov/a4norm:latest serve
```

`linux/amd64` and `linux/arm64`, no ghostscript. The image runs the same
binary as the Linux builds here, so its output is byte-identical to a local
run.

## Speed

Per page at 200 dpi, on an M4 Max:

| input | time |
|---|---|
| invoice photo, rectified | 0.3 s |
| notebook photo | 0.3–0.5 s |
| 12 MP phone photo | 0.5 s |
| ID card, front and back | 0.2 s |

The Python and ImageMagick version this replaces took 11–31 s a page. The same
code also runs in a browser as WebAssembly: [malahov.io](https://malahov.io)
scans on the device, with nothing uploaded.

## Use it directly

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
| rectify the sheet's quadrilateral | a photo shot at an angle is a trapezoid on a desk; no amount of cropping fixes that, and every later step assumes a flat page |
| erase what is connected to the frame edge | desk, shadow and spiral binding reach the border — sheet content never does, so ink is untouchable by construction |
| trim the photographic border | the desk, the shadow line and the sheet's own edge are not part of the document |
| flat-field the illumination | uneven camera light becomes even white paper — this is the step that makes it read as a scan |
| deskew above 0.4°, under 5°, *after* the flat-field | the angle is measured on a binarized copy; on a dim photo the whole sheet falls below the threshold and a real tilt measures as 0.0° |
| neutralize the ink cast, keep coloured ink | a photo tints black print warm; a blue signature or a red stamp must stay coloured |
| tone by histogram percentiles | adapts to the actual file instead of a curve tuned on one photo |
| erase bright featureless haze | a soft shadow or a finger disappears; anything with structure survives |
| clean paper to pure white | with a 1 px guard ring around every glyph |
| fit to A4 | from the real sheet edges when visible, otherwise from the ink block and standard margins |

Every parameter is a flag; `--dry-run` prints what it decided and why.
See [skills/a4norm/SKILL.md](skills/a4norm/SKILL.md) for the symptom → flag table.

## Limits

- Rectification needs the sheet to stand out: bright and low-chroma against a
  darker or coloured surface. White paper on a white desk does not separate, the
  quad is refused with a reason, and the keystone stays.
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
