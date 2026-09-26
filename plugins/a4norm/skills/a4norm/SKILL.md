---
name: a4norm
description: >
  Turn a photo of a paper document into a clean A4 PDF that looks scanned on a
  flatbed: even white paper, neutral ink, no desk or shadow around the sheet,
  exact A4 page, small file. Works on JPG/PNG/HEIC and on PDFs that are really
  just a photo. Triggers on: "make a scan", "scan this document", "photo to
  PDF", "clean up this scan", "normalize to A4", "fit to A4", "сделай скан",
  "приведи к А4", "почисти скан", "/a4norm", "/scan".
argument-hint: "FILE [FILE ...] [-o out.pdf] [--gray] [--format pdf|jpg]"
allowed-tools:
  - Bash
  - Read
  - AskUserQuestion
---

# a4norm — photo of a document → scanner-grade A4 PDF

One program does the whole job: `scripts/a4norm`, a native binary (the Rust
port of the original Python script). **Run it first, look at the result, tune
only if something is actually wrong.** Do not rebuild the pipeline by hand —
every parameter it uses is already exposed as a flag.

## Resolve the binary

```bash
A4NORM=""
for c in "${CLAUDE_PLUGIN_ROOT:-/nonexistent}/skills/a4norm/scripts/a4norm" \
         "$HOME/.claude/skills/a4norm/scripts/a4norm" \
         "$(command -v a4norm 2>/dev/null)"; do
  [ -x "$c" ] && "$c" --help >/dev/null 2>&1 && A4NORM="$c" && break
done
[ -n "$A4NORM" ] || { echo "a4norm not found"; exit 1; }
```

`scripts/a4norm` starts the build for this machine from `scripts/bin/`:
macOS on Apple silicon or Intel, Linux on x86_64 or arm64 (static, any
distribution). Each is about 2.5 MB and needs nothing else for JPEG, PNG and
WebP: it decodes, rectifies, tones and writes the PDF itself — no ImageMagick,
no Python, no ghostscript. All four give the same bytes. Two inputs still call
out to a tool:
- **HEIC** goes through `magick` or `heif-convert`, whichever is installed;
- **PDF** input goes through poppler (`pdfinfo`, `pdfimages`, `pdftoppm`).
On macOS: `brew install imagemagick poppler` covers both.

Anywhere else, build it from the repository
(`cargo install --git https://github.com/georg-malahov/a4norm a4norm-rs --features par`,
which puts `a4norm` on the PATH), or run the public image, whose output is the
same: `docker run --rm -v "$PWD:/work" ghcr.io/georg-malahov/a4norm FILE`.

Expect well under a second per page on an Apple M-series Mac, a couple of
seconds for a 50 MP photo — the Python script took 11–31 s.

The tool lives on its own at **github.com/georg-malahov/a4norm**; the builds
here are copies of its main — the Linux ones out of the public image, the macOS
ones built from `a4norm-rs/` with `cargo build --release --locked --features par`
(plus `--target x86_64-apple-darwin` for Intel). Replace all four and
`a4norm-serve` together: a stale copy fails in ways that look like a bug in the
pipeline.

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

- **Several photos of one document combine into ONE multi-page PDF** — page
  order is argument order. This is the normal case, not the exception: a
  contract is rarely one page. `--separate` gives one document per input
  instead.
- `-o "<name>.pdf"` — with several inputs this is the combined document. Name
  the file after what the document *is*; ask the user if the subject is unclear.
- `--format jpg` — images instead of a PDF (numbered when there are several
  pages). PDF is the default and usually what is wanted.
- `--gray` — grayscale output, ~25% smaller. Colour is the default and keeps a
  blue signature or a red stamp coloured while neutralizing the rest.
- `--dry-run` — analyze and print the report without writing anything. Good for
  explaining what will happen, or for debugging a bad result.
- A multi-page PDF in, a multi-page A4 PDF out.

## What it does, in order

1. **Rasterize.** For a PDF it extracts the embedded image rather than rendering
   it — rendering applies the ICC profile and flattens the tonal range.
2. **Rectify** (`--rectify`, auto). Finds the sheet as a quadrilateral — the big
   bright low-chroma region, both tests relative to the image's own paper level
   — and warps it flat. This is what makes a photo shot at an angle come out as
   a scan instead of a trapezoid on a desk, and it runs first because every
   later step assumes a flat page. A quad is only accepted if it really looks
   like a sheet: 15–90% of the frame, filling ≥80% of its own hull, corners
   between 45° and 135°, opposite sides within 1.8×. Anything short of that is
   refused with a reason in the report, and the rest of the pipeline carries on
   as before — rectifying on a wrong quad is far worse than not rectifying.
   After a rectify it **erases whatever leans in from outside the
   sheet**: non-paper that is *connected to the frame edge* is desk, shadow or a
   spiral binding, so it is flooded from the border and repainted in the page's
   own paper tone, and a thick band of it (a binding) is cropped away. Sheet
   content cannot reach the border, so ink is untouchable by construction.
   **An open booklet (a passport spread) is looked for first** (`--spread`,
   auto): two facing pages — two paper regions of similar size, or one region
   whose long edges both bend or step at the fold — each page's edges fitted
   as support lines (a thumb's curved outline cannot win), the fold where the
   pages' edges meet, each page warped to one common size and joined. A finger
   at the outer edge is repainted in its page's tone (never near the spine,
   where the red perforation strip is skin-coloured). When the strict paper
   mask finds no spread, a looser one (chroma ≤100, for pink pages) and Otsu's
   brightness split (a booklet in its own shadow) get a say. The spread is then
   **turned upright from its own pages**: text direction by ink runs, and up
   vs down by the face photo, which sits on the LEFT of its page (RU page 3,
   every ICAO data page). The report says when it had nothing to decide by.
   **ID-1 cards** (`--cards`, auto): an ID card, a driving licence, a bank
   card is 85.60×53.98 mm, 1.586:1, and that proportion is how a card is
   told from a sheet (1.414) or a passport page (1.42). One or two cards per
   photo; two touching card-shaped regions are left to the spread detector,
   and a lone card beats a spread only if it covers 70% of it. Each card is
   rectified to its real size, turned so its face photo is on the left
   (measured in the photo's known place and its mirror, never searched), a
   finger at its edge repainted, toned as a colour copy (nothing whitened),
   and given rounded corners and a hairline edge. Cards are laid out front
   above back on ONE A4, from one photo or two photos in a row;
   `--card-size fit` fills the page width. The shape decides; a face photo
   (found in its place, or far darker than the mirror place) only decides
   which side is on top. A card beats a spread only if the spread was one
   region cut at a kink.
   **Edges when brightness fails** (`--edges`, auto): Canny on brightness
   and saturation, Hough lines, every pair-of-pairs outline scored by how
   much of it is edge. Believed only when brightness found nothing, a scrap
   inside the outline, or the whole frame. Card-shaped → card path; with a
   lone fold line across the middle → spread; else a sheet (≥60% edge,
   15–85% of the frame, 1.25–1.6). This is what finds a white page on a
   white desk and a passport over a light floor. A spread's orientation and
   its face photo are now looked for in the photo's known place (left third
   of the lower page), and the photo box is grown to passport-photo height.
3. **Or decide the frame holds no document.** No accepted quad *and* a
   paper-like area under `--photo-paper` (20%) means somebody is turning
   snapshots into a PDF, not scanning. This is decided BEFORE anything touches
   the pixels, and the photo path is a single early return — the only things
   that happen are the geometric fit onto the page and the JPEG encode at
   `--photo-dpi` (200) and `--photo-quality` (82) with 4:2:0 chroma. No
   flat-field, no tone, no haze filter, no paper-whitening, no ink
   neutralisation, no sharpen, and `--gray` does not apply either (the run says
   so rather than ignoring it silently). A landscape photo turns the page
   rather than being rotated. Measured paper-like area is 9% for a photo of a
   screen against 40–83% for every real document and test page, so the
   threshold sits in a wide gap — but say so in the report, because the user
   may disagree. `--photo off` forces the scanner treatment, `--photo on`
   forces the short path. Note the test is only consulted when no sheet quad
   was accepted: a snapshot of a whiteboard or a lit screen gets rectified and
   scanned however small its paper-like area is, and `--photo on` is the way
   out.
4. **Orient** — EXIF only. `--rotate auto` turns NOTHING: a wide result is laid
   on a landscape A4 instead, because the page turning costs nothing and the
   picture turning makes the text unreadable. A square notebook page shot in a
   wide frame is wide because of the FRAME, not because the sheet is sideways.
   `--rotate 90/180/270` still turns the picture, and the page follows it;
   `--landscape` forces a landscape page; sides within `--rotate-tol` count as
   square and leave the page portrait.
5. **Trim the photographic border** — skipped after a rectify, which already
   ended exactly at the sheet. Finds the sheet edge on each side by a hard
   brightness step whose outer strip does not look like the page, then cuts a
   little further in to drop the edge shadow.
5.  **An open passport is a colour copy** — like a card: light evened, tint,
    guilloche and ornament kept, nothing whitened; the whitening steps do
    not run on it (`--spread-scan` restores the old scan look). Fingers are
    told from red ornament by texture (smooth skin vs patterned print).
5a. **Keep a face photo out of the paper treatment** (sheets only) — a compact block of
    cells darker than the paper near them, portrait-sized, ≥40% of its box.
    It is cut out before the flat-field, toned on its own and laid back with a
    feathered edge; otherwise the face comes out with white holes for cheeks.
    `--no-keep-photo` turns it off. Skipped (and reported) if the page is
    deskewed afterwards.
6. **Flat-field.** Divides by a heavily smoothed background estimate, which is
   what turns uneven camera light into even white paper.
7. **Deskew** — skipped after a rectify (the quad already set the
   orientation) — if the text is off by more than `--deskew-min` (0.4°) and under 5°
   — deliberately *after* the flat-field, because the angle is measured on a
   binarized copy and a dim photo reads as one solid blob, so a real tilt comes
   out as 0.0°. Rotation swings a strip of desk back into frame, so a cut of
   `max_side × sin(angle)` follows on every side that had a detected edge.
8. **Neutralize the ink.** A photo tints black print warm. Everything is pushed
   to neutral grey except pixels that are both high-chroma and dark — real
   coloured ink, any hue — which keep their colour.
9. **Tone** by histogram percentiles (`-contrast-stretch`), not a fixed curve.
10. **Erase leftover haze** — bright *and* featureless areas become paper, so a
   soft shadow or a finger at the edge disappears while anything with structure
   (ink, a faint stamp, a pencil note) survives.
11. **Clean paper to pure white** at `--paper-thr` (80%), protecting a 1 px
    ring around every glyph. Aggressive on purpose: it is what erases the ghost
    of the other side of the page, and measured on printed text it changes ink
    coverage by 0.04%.
12. **Fit to A4** (see below) and write JPEG-in-PDF at `--dpi` (300) and
    `--quality` (88, no chroma subsampling — text stays crisp). When the photo
    holds under 180 dpi of real detail at the size it lands, the page is
    written at 200 dpi with 4:2:0 instead (a 1280×960 passport snapshot: 1.6 MB
    → 577 KB, no visible difference). An explicit `--dpi` is always obeyed.

13. **Clean the open paper** — small (<2.5 mm), light (nothing darker than
    60%) marks with no print within 3 mm are erased: shadow grain in a
    corner, dust, a pencil fleck. A full stop sits next to print and stays;
    long thin fragments (a light ruled line) count as print. A large light
    mark filling a page corner is a shadow and goes too, except around print
    it covers. About 1.5–2 s a page; `--no-despeckle` turns it off.

## How the A4 scale is chosen (`--fit`, default `auto`)

| Mode | When it applies | How the scale is derived |
|---|---|---|
| photo | the frame holds no document | the picture is fitted as shot, page turned for a landscape one |
| rectified | the page was warped flat in step 2 | the rectified image *is* the sheet, so it is fitted to the page whole |
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
| a wide page landed on a landscape sheet and portrait was wanted | `--rotate 90` — it turns the picture, and the page follows it |
| the page came out sideways (the sheet really was photographed sideways) | `--rotate 90` / `180` / `270` |
| a handwritten page came out tilted, or the run tilted it | `--no-deskew` — the estimator reads text baselines, and handwriting has none worth trusting |
| the page was shot at an angle and came out as a trapezoid | the quad was refused — the report says why. `--rectify on` fails loudly instead of carrying on, which is the quickest way to see the reason |
| rectification fired on something that is not a sheet | `--rectify off` |
| a binding or a desk edge survived along one side | `--edge-band 15` (how far in the border flood may reach) |
| a form's shaded panel got erased, or the page lost a whole column at one edge | it was judged desk — `--band-dark 75`, or `--band-structure 3` |
| a shaded panel survived but its outermost few mm went white | `--edge-keep 0.5` |
| a binding or dark desk band stayed after a rectify | it was judged document — `--band-dark 45`, or `--band-structure 10` |
| a spiral binding survived as dark marks in the margin | its rings were not regular enough to be recognised as a binding (the test wants ≥6 equal blobs at an equal pitch over 25–75% of the side) — `--band-dark 45` judges the band on darkness alone |
| a regular row of printed marks at one edge got cut as a binding | `--band-dark 75` to keep the band, or `--edge-keep 8` to keep most of it |
| part of the page was repainted as if it were desk | `--no-edge-clean` |
| tiny light marks on open paper vanished (faint dots, a light dotted line) | `--no-despeckle` |
| file too big | `--dpi 200`, `--quality 80`, or `--gray` |
| a passport spread came out as one page, or its facing page was dropped | `--spread on` fails loudly with each paper mask's reason |
| something that is not a booklet was split and joined as a spread | `--spread off` |
| a spread came out upside down | no face photo to tell up from down — `--rotate 180` |
| an ID card came out as a scanned page | not found as a card (no `card:` line) — too like its background |
| a card's back landed on top | no face found on either side; input order kept — shoot the front first |
| a card's front and back landed on two pages | the two photos were not in a row, or one was not found as a card |
| cards too small to read | `--card-size fit` |
| something that is not a card was laid out as one | `--cards off` |
| the page was cropped to a wrong rectangle "found by its edges" | `--edges off` |
| a face photo came out bleached | it was not found — no `face photo at` line in the report |
| a dark picture on a page kept a grey box around it | taken for a face photo — `--no-keep-photo` |

`--dry-run` after a change shows the new decisions without writing a file.

## As a service

The same image runs an HTTP front end for anything that is not a shell —
`scripts/a4norm-serve`, stdlib Python, which runs the binary once per request:

```bash
a4norm-serve --port 8080 --max-concurrency 1      # or: docker run … a4norm serve
curl -X POST http://localhost:8080/scan -F p1=@page1.HEIC -F p2=@page2.HEIC -o doc.pdf
```

`GET /health`, `POST /scan` (multipart, any field names, several parts → one
multi-page PDF; `?format=jpg` for a single image). Any a4norm flag passes
through as a query parameter. Concurrency is capped because each page uses
every core it is given.

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

- **Rectification needs the sheet to stand out from the background.** Bright and
  low-chroma against a darker or coloured surface works; white paper on a white
  desk does not separate, the quad is refused, and the keystone stays. Reshoot
  square-on or on a darker surface.
- **A card must stand out from what it lies on too** — on a white surface,
  light wood or over a bright background it is scanned as a document. A
  card's back has no face photo, so it keeps its orientation as shot.
- **A spread or card must stand out from its background by brightness, colour
  or a clear straight edge.** Edge finding rescued white-on-white passports;
  a card on white paint, over bright railings or on light wood, and a
  booklet whose hand hides a corner, are still missed.
- **Pages are processed independently**, so the scale can differ by a few tenths
  of a percent between pages of one document.
- **The haze filter can eat a genuinely smooth light-grey fill.** `--no-haze`.
- **The `content` fit assumes ordinary margins.** A form printed edge to edge
  needs `--fit frame` or explicit `--margins`.

## Local test corpus

Real documents never go into the repository. In the repo (`~/projects/a4norm`),
`tests/run.sh --open` runs the public examples (`tests/regression.py`: structure
+ golden snapshots, also in CI) and the git-ignored local corpus
(`tests/corpus/` + `cases.json`, via `tests/corpus.py`), then builds and opens
`tests/out/report.html`: every input beside its result and golden, verdict and
why. Add new hard photos to `tests/corpus/`, named for what makes them hard; a
photo not handled yet is marked `known_fail`. Never put a user's own documents
there.

## Handing back

Report the output path, the file size versus the source, and which fit mode was
used. If anything was tuned away from the defaults, say which flag and why, so
the next run on a similar photo can start there.
