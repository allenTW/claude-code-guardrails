# claude-code-guardrails

Three small hooks that keep Claude Code honest and out of trouble. Python 3.9, standard library only.

| Hook | Event | What it does |
|---|---|---|
| `stop_gate.py` | Stop | Blocks the stop once if this session left open checklist items (`- [ ]`), dirty files it wrote (Edit/Write and Bash `>`, `>>`, `tee`, `sed -i`, `cp`, `mv`), commits not pushed, or a final report that lists doable work as "not done". |
| `reserve_guard.py` | PreToolUse (Agent/Task) | Requires a model name on sub-agents and denies them when the quota snapshot is above a threshold. Optional "delegate first" check. |
| `bash_guard.py` | PreToolUse (Bash) | Denies `osascript`, `screencapture` and `~/Downloads` access run directly from a session, pointing at a permission proxy (see the sibling `macos-tcc-proxy` repo). |

Design rules: block at most once per stop, fail open on any error, real blockers (publishing, money, keys, no hardware) are never treated as laziness. Every decision is logged as JSONL under `$GUARDRAILS_HOME` (default `~/.claude-guardrails`).

## Install

```bash
./install.sh            # copies the hooks to ~/.claude-guardrails (does not touch your settings)
```

Then merge `examples/settings.json` into `~/.claude/settings.json` and replace the paths.
Optional: write `<GUARDRAILS_HOME>/quota.json` as `{"limits":{"at":<epoch>,"five_hour":{"used_percentage":42}}}` for reserve_guard.

## Test

```bash
python3 -m pip install pytest   # only the tests need it; the hooks use the standard library
python3 -m pytest -q
```

## Limits (honest list)

- Bash write detection is best effort: a Python script that writes files internally is invisible to it.
- Report-text checks are keyword based; expect some false positives and misses.
- It checks that you wrapped up, not that the work is correct.
- Files under a path containing `/tmp/` or `scratchpad` are treated as scratch space and never block a stop. If a test repo of yours lives there, move it, or the hook will look like it does nothing.

## 繁體中文簡介

三個 Claude Code hook：`stop_gate`（收工前檢查清單未勾、寫過卻未 commit／push、把做得到的事列成「未做」，每次最多擋一次、任何錯誤一律放行）、`reserve_guard`（額度吃緊時擋子代理、要求指定 model）、`bash_guard`（擋直接呼叫 osascript／screencapture／~/Downloads，導向權限代理）。安裝：執行 `install.sh`，再把 `examples/settings.json` 合併進你的 settings 並替換路徑。測試：`python3 -m pytest -q`。

## License

MIT, see `LICENSE`.
