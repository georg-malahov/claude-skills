#!/bin/bash
# append to the ralph progress file with a timestamp
# usage: append-progress.sh <progress-file> [message]
#   message provided  -> appends one timestamped line
#   no message        -> reads stdin, appends all lines (multi-line content)
# copied from umputun/cc-thingz planning/exec.

set -e

if [ $# -lt 1 ]; then
    echo "error: usage: append-progress.sh <file> [message]" >&2
    exit 1
fi

file="$1"
shift

if [ ! -f "$file" ]; then
    echo "error: progress file not found: $file" >&2
    exit 1
fi

if [ $# -gt 0 ]; then
    # single line with timestamp
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$file"
else
    # multi-line from stdin
    cat >> "$file"
fi
