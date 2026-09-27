#!/usr/bin/env bash
# The whole pipeline on a toy app, end to end: two "builds" served side by
# side (app/before = main, app/after = the branch), two scenarios recorded on
# each, three measuring runs per side, a 2x2 video and the numbers table.
#
#   bash examples/run.sh [OUT_DIR]        # default: $TMPDIR/ba-example
#
# Needs node 18+, python3 (static server), ffmpeg, and playwright + sharp that
# node can find: run from a project that has them, or
#   npm i --prefix ~/.cache/ba playwright sharp && npx --prefix ~/.cache/ba playwright install chromium
#   BA_NODE_PATH=~/.cache/ba bash examples/run.sh
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
S="$HERE/../scripts"

if [ "${1:-}" = "--record" ]; then # called back by serve-pair once both servers answer
  OUT=$2
  for side in before after; do
    url=$([ $side = before ] && echo "$BEFORE_URL" || echo "$AFTER_URL")
    node "$S/screenplay.mjs" --scenario "$HERE/filter.scenario.mjs" --side $side --url "$url" \
      --out "$OUT/filter" --throttle 4 --hud
    node "$S/screenplay.mjs" --scenario "$HERE/camera.scenario.mjs" --side $side --url "$url" \
      --out "$OUT/camera" --camera "$OUT/cam.mjpeg" --caption-pos top
    node "$S/screenplay.mjs" --scenario "$HERE/filter.scenario.mjs" --side $side --url "$url" \
      --out "$OUT/filter-runs" --throttle 4 --runs 3 --no-video
  done
  exit 0
fi

OUT=${1:-${TMPDIR:-/tmp}/ba-example}
mkdir -p "$OUT"
node "$S/fake-camera.mjs" --image "$HERE/document.svg" --out "$OUT/cam.mjpeg"
node "$S/serve-pair.mjs" \
  --before 'python3 -m http.server $PORT' --before-cwd "$HERE/app/before" \
  --after  'python3 -m http.server $PORT' --after-cwd  "$HERE/app/after" \
  --path /index.html --logs "$OUT/logs" \
  -- bash "$0" --record "$OUT"
node "$S/compose.mjs" --out "$OUT/before-after.mp4" --align ready --frames 4 \
  --title "Two fixes, before → after" \
  --subtitle "Row 1: the filter's ranking moved to a worker\nRow 2: the photo is taken at the press" \
  "$OUT/filter/before.webm" "$OUT/filter/after.webm" "$OUT/camera/before.webm" "$OUT/camera/after.webm"
{
  node "$S/table.mjs" "$OUT/filter-runs/before.json" "$OUT/filter-runs/after.json" --segments typing
  echo
  node "$S/table.mjs" "$OUT/camera/before.json" "$OUT/camera/after.json" --metrics custom.shutterLagMs
} | tee "$OUT/numbers.md"
echo "video: $OUT/before-after.mp4"
