# Configuration

Everything below exists in the code. There is no config file format beyond these.

## Environment variables

| Variable | Used by | Default | Meaning |
|---|---|---|---|
| `GUARDRAILS_HOME` | `stop_gate`, `reserve_guard`, `install.sh` | `~/.claude-guardrails` | Folder for hooks, state and logs. |
| `MAC_PROXY` | `bash_guard` | `~/.mac-proxy/mac_proxy.py` | Path of the proxy client shown in the denial message. Only affects the text. |

## Files under `GUARDRAILS_HOME`

| Path | Read/written by | Meaning |
|---|---|---|
| `todo/<session_id>.md` | read by `stop_gate` | Checklist file. Every line starting with `- [ ]` counts as an open item. Mark done as `- [x]`. |
| `logs/stop_gate.jsonl` | written by `stop_gate` | One JSON line per Stop event: session id, event keys, whether it blocked, the problems. |
| `quota.json` | read by `reserve_guard` | `{"limits": {"at": <epoch seconds>, "five_hour": {"used_percentage": N}, "seven_day": {"used_percentage": N}}}`. Written by you (for example from a status-line script). Ignored if `at` is older than 20 minutes. |
| `reserve-off` | read by `reserve_guard` | If this file exists, the quota check is skipped (the model-name and delegate-first checks still run). |
| `delegate-log.jsonl` | read by `reserve_guard` | Enables the delegate-first check. Lines like `{"ts": "2026-10-19T12:00:00", "exit": 0}`; the newest parseable line decides. |

`install.sh` creates `todo/` and `logs/` and copies the three scripts.

## Constants in the code

Edit the script to change these (no env override exists).

| Constant | File | Value | Meaning |
|---|---|---|---|
| `AGENT_AT` | `reserve_guard.py` | 90 | five-hour percentage at which `Agent`/`Task`/`Workflow` are denied |
| `HEAVY_AT` | `reserve_guard.py` | 95 | five-hour percentage at which other non-allowed tools are denied |
| `WEEK_AT` | `reserve_guard.py` | 95 | seven-day percentage at which everything non-allowed is denied, agents included |
| `STALE_SEC` | `reserve_guard.py` | 1200 | snapshot age after which it is ignored |
| `DELEGATE_WINDOW_SEC` | `reserve_guard.py` | 1800 | how recent a delegation log entry must be |
| `NO_DELEGATE_MARK` | `reserve_guard.py` | `NO_DELEGATE:` | line in the sub-agent prompt that skips the delegate-first check |
| `ALLOW` | `reserve_guard.py` | Read, Grep, Glob, Write, Edit, TodoWrite, ToolSearch, AskUserQuestion, SendUserFile, PushNotification | never denied by the quota check |
| `LAZY` | `stop_gate.py` | list of (regex, label) | phrases that put doable work in the "not done" column; add your own |
| `EXEMPT` | `stop_gate.py` | regex | lines naming a real blocker; these never count |
| `FIELD` | `stop_gate.py` | regex | lines saying the user need not do something |
| `SKIP_PATH_PARTS` | `stop_gate.py` | `/tmp/`, `scratchpad` | paths containing these never count as unfinished work |
| `WRITE_CMDS` | `stop_gate.py` | cp, mv, install, rsync | commands whose last argument is treated as a written file |

## Hook settings

See `examples/settings.json`. The matcher for `reserve_guard` is `*` because it also checks the quota for every tool; `bash_guard` uses `Bash`; `Stop` hooks take no matcher. The `timeout` values in the examples (15 s for `stop_gate`, which runs `git`; 5 s for the others) are suggestions.
