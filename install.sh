#!/bin/sh
# Copy the three hooks to ~/.claude-guardrails (or $GUARDRAILS_HOME). Then merge examples/settings.json
# into ~/.claude/settings.json by hand (this script never edits your settings).
set -e
SRC=$(cd "$(dirname "$0")" && pwd)
DST=${GUARDRAILS_HOME:-$HOME/.claude-guardrails}
mkdir -p "$DST/todo" "$DST/logs"
cp "$SRC"/guardrails/stop_gate.py "$SRC"/guardrails/reserve_guard.py "$SRC"/guardrails/bash_guard.py "$DST"/
echo "installed to $DST"
echo "next: merge $SRC/examples/settings.json into ~/.claude/settings.json"
