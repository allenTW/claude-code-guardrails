# Examples

| File | What it is |
|---|---|
| `settings.json` | All three hooks (merge into `~/.claude/settings.json`). |
| `settings.bash-guard-only.json` | Only `bash_guard` (PreToolUse on Bash). |
| `settings.stop-gate-only.json` | Only `stop_gate` (Stop). |
| `output/*.json` | Real stdout captured by feeding a sample event to each hook (see below). |

The `output/` files were produced by piping a small JSON event into the script, for example:

```bash
echo '{"session_id":"demo","last_assistant_message":"Not done:\n- I have not run the tests."}' \
  | GUARDRAILS_HOME=$(mktemp -d) python3 guardrails/stop_gate.py
```

| Output file | Input event |
|---|---|
| `stop_gate_open_checklist.json` | session has a checklist file with one `- [ ]` line left |
| `stop_gate_lazy_report.json` | final message lists "not run the tests", "not committed" and "want me to continue" |
| `bash_guard_osascript.json` | Bash command `osascript -e ...` |
| `bash_guard_downloads.json` | Bash command that lists the Downloads folder |
| `reserve_guard_no_model.json` | `Agent` call without a `model` |
| `reserve_guard_quota.json` | `quota.json` snapshot at 96% five-hour usage, tool `Bash` |

The temporary directory in the quota message was replaced with `~/.claude-guardrails` for readability; nothing else was edited apart from pretty-printing the JSON.
