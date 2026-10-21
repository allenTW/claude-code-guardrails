# Changelog

## 0.1.0 - 2026-10-20

First public release.

- `stop_gate.py` (Stop hook): blocks one stop when the session left open checklist items, uncommitted files it wrote, unpushed commits, or a report that lists doable work as "not done".
- `reserve_guard.py` (PreToolUse hook): requires a model name on sub-agents, denies heavy tools near the quota limit, optional delegate-first check.
- `bash_guard.py` (PreToolUse hook on Bash): denies direct `osascript`, `screencapture` and Downloads-folder access.
- `install.sh`, example settings, 39 tests.
