# claude-code-guardrails

![license](https://img.shields.io/badge/license-MIT-blue) ![python](https://img.shields.io/badge/python-3.9%2B-blue) ![tests](https://img.shields.io/badge/tests-39%20passed-brightgreen) ![deps](https://img.shields.io/badge/dependencies-none-lightgrey)

**Three small hooks that stop Claude Code from saying "done" while work is still open, from burning your last quota on sub-agents, and from poking macOS permission prompts.** Python standard library only, no daemon, no network.

| Hook | Event | Blocks |
|---|---|---|
| [`stop_gate.py`](guardrails/stop_gate.py) | `Stop` | Finishing with open `- [ ]` items, files the session wrote but never committed, commits never pushed, or a report that lists doable work as "not done". |
| [`reserve_guard.py`](guardrails/reserve_guard.py) | `PreToolUse` (all tools) | Sub-agents with no `model`, and heavy tools once your 5h / 7d quota snapshot is nearly used up. |
| [`bash_guard.py`](guardrails/bash_guard.py) | `PreToolUse` (Bash) | Direct `osascript`, `screencapture` and Downloads-folder access that makes macOS re-ask for permission after every Claude Code update. |

## Quick start (about 30 seconds)

```bash
git clone https://github.com/allenTW/claude-code-guardrails
cd claude-code-guardrails
./install.sh        # copies the three hooks to ~/.claude-guardrails; never edits your settings
```

Then merge [`examples/settings.json`](examples/settings.json) into `~/.claude/settings.json` (or pick a smaller one: [`bash_guard` only](examples/settings.bash-guard-only.json), [`stop_gate` only](examples/settings.stop-gate-only.json)) and restart Claude Code.

Check the wiring without Claude:

```bash
echo '{"session_id":"t","last_assistant_message":"Not done:\n- I have not run the tests."}' \
  | GUARDRAILS_HOME=$(mktemp -d) python3 ~/.claude-guardrails/stop_gate.py
```

It should print a `{"decision": "block", ...}` line.

## What each hook does

### stop_gate (Stop)

Runs when Claude is about to stop. It blocks that stop **once** if, for this session only (other sessions editing the same repo are ignored):

1. a checklist is open (`TodoWrite` items not completed, or `- [ ]` lines in `<GUARDRAILS_HOME>/todo/<session_id>.md`),
2. a file the session wrote (Edit/Write, or Bash `>`, `>>`, `tee`, `sed -i`, `cp`, `mv`, `install`, `rsync`) is still dirty in git,
3. a repo the session ran `git commit` in has unpushed commits,
4. the final report lists doable work as undone ("have not run the tests", "not committed", "want me to continue?", ...), matched in English and Traditional Chinese. Lines naming a real blocker (publishing, payment, credentials, quota, no hardware) are exempt.

Real output when one checklist line is left open ([`examples/output/stop_gate_open_checklist.json`](examples/output/stop_gate_open_checklist.json)):

```json
{
  "decision": "block",
  "reason": "Self-check before reporting failed: unfinished checklist items: run the tests. In order: (1) do what you can do now (run the tests, commit, push, restart, look at the page); (2) if a permission blocks it, say exactly which one; (3) only a real blocker (publishing, money, credentials, missing hardware) may stay in the 'not done' column, with what is blocking it."
}
```

Claude reads the reason, does the work, and the next stop passes (`stop_hook_active` is set, so it can never loop). More: [`stop_gate_lazy_report.json`](examples/output/stop_gate_lazy_report.json).

### reserve_guard (PreToolUse)

- A `Agent`/`Task` call without a `model` is denied: *"Name a model for the sub-agent (haiku / sonnet / opus) and resend."* ([example](examples/output/reserve_guard_no_model.json))
- If `<GUARDRAILS_HOME>/quota.json` holds a fresh rate-limit snapshot, heavy tools are denied at 95% (five-hour or seven-day), and `Agent`/`Task`/`Workflow` already at 90% (five-hour). Read/Grep/Glob/Write/Edit and a few chat-support tools are always allowed. ([example](examples/output/reserve_guard_quota.json))
- Optional delegate-first check, only active if `<GUARDRAILS_HOME>/delegate-log.jsonl` exists.

### bash_guard (PreToolUse on Bash)

Denies `osascript ...`, `screencapture ...` and `~/Downloads` access typed straight into a session, and tells Claude to use a permission proxy instead. Mentions inside `grep`, `echo`, markdown or heredoc bodies pass. ([example](examples/output/bash_guard_osascript.json))

macOS records a privacy grant under the process that asks; a process Claude spawns is attributed to the Claude Code binary, whose path contains its version number, so the prompt returns after each update. Route those calls through a stable proxy client and point `MAC_PROXY` at it (default `~/.mac-proxy/mac_proxy.py`; see the sibling `macos-tcc-proxy` repo).

## Configuration

All settings are environment variables and plain files under `GUARDRAILS_HOME` (default `~/.claude-guardrails`). See [docs/configuration.md](docs/configuration.md). Decisions of `stop_gate` are logged as JSON lines in `<GUARDRAILS_HOME>/logs/stop_gate.jsonl`.

## FAQ

**Will it ever trap me in a loop?** No. `stop_gate` blocks at most once per stop, and every hook allows on any internal error.

**It does nothing in my test repo.** Files under a path containing `/tmp/` or `scratchpad` are treated as scratch space and never block a stop.

**I hit the quota reserve but must continue.** `touch ~/.claude-guardrails/reserve-off` (the denial message tells you this too).

**Does it work on Linux?** `stop_gate` and `reserve_guard` have no macOS-specific code. `bash_guard` only matters on macOS.

**Is this a safety boundary?** No. Bash write detection is best effort (a Python script that writes files internally is invisible), and report checks are keyword based, so expect false positives and misses. It checks that you wrapped up, not that the work is correct.

## Docs

- [How it works](docs/how-it-works.md)
- [Configuration](docs/configuration.md)
- [Examples](examples/README.md)
- [Contributing](CONTRIBUTING.md), [Changelog](CHANGELOG.md)

Tests: `python3 -m pip install pytest && python3 -m pytest -q tests` (39 tests, Python 3.9.6).

## 繁體中文簡介

三個 Claude Code hook：`stop_gate`（收工前檢查清單未勾、寫過卻未 commit／push、把做得到的事列成「未做」，每次最多擋一次、任何錯誤一律放行）、`reserve_guard`（子代理必須指定 model、額度吃緊時擋重型工具）、`bash_guard`（擋直接呼叫 osascript／screencapture／Downloads，導向權限代理）。安裝：執行 `./install.sh`，再把 `examples/settings.json` 合併進 `~/.claude/settings.json`。測試：`python3 -m pytest -q tests`。

## License

MIT, see [LICENSE](LICENSE).
