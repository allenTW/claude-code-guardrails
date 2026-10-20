#!/usr/bin/env python3
"""PreToolUse hook (matcher "*"): keep the last slice of your 5h / 7d quota for plain chat, and make
sub-agent use deliberate.

1. Quota reserve. Reads a rate-limit snapshot JSON (default <GUARDRAILS_HOME>/quota.json), for example
   written by a statusLine script from Claude Code's rate-limit fields:
       {"limits": {"at": 1760000000, "five_hour": {"used_percentage": 91}, "seven_day": {"used_percentage": 40}}}
   Past the caps below, heavy tools are denied so what is left stays for conversation.
   A snapshot older than STALE_SEC is ignored. Override: touch <GUARDRAILS_HOME>/reserve-off
2. Sub-agents must name a model (haiku / sonnet / opus) - no silent default.
3. Optional delegate-first (off unless <GUARDRAILS_HOME>/delegate-log.jsonl exists): a non-haiku sub-agent is
   denied unless your delegation tool logged a run in the last 30 minutes, or the prompt has a line
   "NO_DELEGATE: <reason>". The log is JSON lines {"ts": "2026-10-19T12:00:00", "exit": 0}.
   If the log file is missing the check is skipped (it never blocks over its own breakage).
"""
import json
import os
import sys
import time

HOME = os.environ.get("GUARDRAILS_HOME") or os.path.join(os.path.expanduser("~"), ".claude-guardrails")
AGENT_AT = 90      # Agent/Workflow fan out, so stop them earlier
HEAVY_AT = 95      # everything heavy
WEEK_AT = 95       # seven-day window, agents included
STALE_SEC = 20 * 60
DELEGATE_WINDOW_SEC = 30 * 60
NO_DELEGATE_MARK = "NO_DELEGATE:"
ALLOW = {"Read", "Grep", "Glob", "Write", "Edit", "TodoWrite", "ToolSearch",
         "AskUserQuestion", "SendUserFile", "PushNotification"}


def main():
    quota_off = os.path.exists(os.path.join(HOME, "reserve-off"))
    try:
        event = json.load(sys.stdin)
        tool = event.get("tool_name", "")
    except Exception:
        return
    tool_input = event.get("tool_input") or {}
    if tool in ("Agent", "Task"):
        if not tool_input.get("model"):
            return deny("Name a model for the sub-agent (haiku / sonnet / opus) and resend.")
        reason = delegate_first(tool_input)
        if reason:
            return deny(reason)
    if quota_off:
        return
    try:
        with open(os.path.join(HOME, "quota.json")) as f:
            limits = json.load(f)["limits"]
    except Exception:
        return
    if tool in ALLOW or time.time() - limits.get("at", 0) > STALE_SEC:
        return
    agent = tool in ("Agent", "Task", "Workflow")
    used = 0
    for w in ("five_hour", "seven_day"):
        u = (limits.get(w) or {}).get("used_percentage") or 0
        cap = WEEK_AT if w == "seven_day" else (AGENT_AT if agent else HEAVY_AT)
        if u >= cap:
            used = max(used, u)
    if not used:
        return
    deny("Quota reserve mode (%d%% used): chat and notes only, do not retry other tools. "
         "Start a new session or /clear to chat. Lift it: touch %s" % (used, os.path.join(HOME, "reserve-off")))


def recent_delegation(now=None, path=None):
    """True if the delegation log has an entry in the last window. A missing log counts as True."""
    path = path or os.path.join(HOME, "delegate-log.jsonl")
    now = now or time.time()
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - 65536))
            lines = f.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return True
    for line in reversed(lines):
        try:
            d = json.loads(line)
            ts = time.mktime(time.strptime(d["ts"][:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
        except (ValueError, KeyError):
            continue
        return now - ts <= DELEGATE_WINDOW_SEC
    return False


def delegate_first(tool_input, now=None, log_path=None):
    """Return a denial reason, or None to allow."""
    model = (tool_input.get("model") or "").lower()
    if "haiku" in model:
        return None
    if NO_DELEGATE_MARK in (tool_input.get("prompt") or ""):
        return None
    if recent_delegation(now, log_path):
        return None
    return ("Delegate first: run your delegation tool before spawning a %s sub-agent. If it cannot be "
            "delegated, add a line '%s <reason>' to the prompt and resend." % (model or "non-haiku", NO_DELEGATE_MARK))


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}))


if __name__ == "__main__":
    main()
