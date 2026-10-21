# How it works

Claude Code runs a hook as a command, writes a JSON event to its stdin and reads JSON from stdout. All three hooks here follow the same rules: print nothing to allow, print one JSON object to intervene, and treat any internal error as "allow".

## Lifecycle

```
tool call requested --> PreToolUse hooks (reserve_guard, bash_guard) --> allow / deny
...work...
Claude wants to stop --> Stop hook (stop_gate) --> allow / block once
```

- PreToolUse denial: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}`. The reason text is shown to Claude.
- Stop block: `{"decision": "block", "reason": "..."}`. The reason is fed back to Claude, which continues working.

## stop_gate.py

1. Read the event. If `stop_hook_active` is true, return: a second stop always passes, so it cannot loop. Any exception is swallowed (fail open).
2. Read the session transcript (`transcript_path`, JSONL), skipping sidechain (sub-agent) entries. From assistant `tool_use` blocks it collects:
   - the latest `TodoWrite` list,
   - files from `Edit`/`Write`/`NotebookEdit`,
   - for `Bash`: redirections (`>`, `>>`), `tee`, `sed -i`, and `cp`/`mv`/`install`/`rsync` (last argument), tracking `cd` and `git -C`; and repos where `git commit` ran.
3. The report is `last_assistant_message` from the event, or else the last assistant text of the final turn in the transcript.
4. Checks, each producing a problem string:
   - open todos: not-`completed` TodoWrite items plus `- [ ]` lines in `<GUARDRAILS_HOME>/todo/<session_id>.md`;
   - dirty files: `git status --porcelain -- <file>` is non-empty for a collected file (files under `/tmp/` or `scratchpad` are skipped);
   - unpushed: `git rev-list --count @{u}..HEAD` is above 0 in a committed repo (no upstream means no finding);
   - lazy report: `lazy_hits()` splits the report on newlines, `。` and `；`; if there is a "Not done" section (heads `not done`, `couldn't do`, `未做`, `沒做完`, `做不到`) only that section plus the last two lines are scanned, text inside 「」 is dropped, and lines matching `EXEMPT` or `FIELD` are skipped. Remaining lines are matched against `LAZY`.
5. If any problem exists it logs a line to `logs/stop_gate.jsonl` and prints the block decision listing the problems.

Limits: a script that writes files internally is not seen; keyword matching misses paraphrases.

## reserve_guard.py

Order of checks for each tool call:

1. Unparseable event: allow.
2. `Agent`/`Task` without `model`: deny.
3. `Agent`/`Task` and `delegate-log.jsonl` exists: a `haiku` model passes; a prompt containing `NO_DELEGATE:` passes; otherwise the newest parseable log line must be at most 30 minutes old, else deny. A missing log file means the check is skipped.
4. If `reserve-off` exists: allow.
5. Load `quota.json`; if unreadable: allow. If the tool is in `ALLOW` or the snapshot is older than 20 minutes: allow.
6. Deny if `five_hour` is at least 95 (90 for `Agent`/`Task`/`Workflow`) or `seven_day` is at least 95.

## bash_guard.py

For a `Bash` event, take `tool_input.command`:

1. Delete heredoc bodies (they are data).
2. If `osascript` or `screencapture` appears in command position (start of line, after `;`, `&`, `|`, `(`, a backtick or `$(`, optionally behind `sudo`, `env`, `nohup`, `time`, `xargs`, variable assignments or a path prefix): deny with proxy usage instructions.
3. Else if the command refers to the Downloads folder via `~`, `$HOME`, `${HOME}` or an absolute home path, and does not contain the text `mac_proxy`: deny.
4. Otherwise allow. A malformed event is allowed.

The regexes are at the top of `guardrails/bash_guard.py`; `tests/test_bash_guard.py` lists the allowed and denied shapes.
