#!/bin/bash
# initialize the ralph progress file with a header
# usage: init-progress.sh <progress-file> <plan-path> <branch-name>
# adapted from umputun/cc-thingz planning/exec. progress files are throwaway
# runtime telemetry and live in /tmp; durable resume state is the session
# manifest + plan checkboxes, not this file.

set -e

file="$1"
plan="$2"
branch="$3"

if [ -z "$file" ] || [ -z "$plan" ] || [ -z "$branch" ]; then
    echo "error: usage: init-progress.sh <progress-file> <plan-path> <branch-name>" >&2
    exit 1
fi

mkdir -p "$(dirname "$file")"

# if the file already exists (resume), append a resume marker instead of clobbering
if [ -f "$file" ]; then
    echo "--- Resumed: $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$file"
    echo "$file"
    exit 0
fi

cat > "$file" <<EOF
# progress
Plan: $plan
Branch: $branch
Started: $(date '+%Y-%m-%d %H:%M:%S')
---
EOF

echo "$file"
