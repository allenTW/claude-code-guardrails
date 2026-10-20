#!/usr/bin/env python3
"""PreToolUse hook (matcher "Bash"): deny osascript / screencapture / ~/Downloads access run straight from a
Claude Code session and point at a permission proxy (see the macos-tcc-proxy repo).

Why: macOS files a privacy grant under the process that asks. A process Claude spawns is attributed to the
Claude Code binary, whose path contains the version number, so macOS asks again after every update. Through
a stable proxy the grant is asked for once.
Only command positions count: `grep osascript x`, `echo screencapture`, a markdown `osascript` and heredoc
bodies pass. Set MAC_PROXY to your proxy client path (default ~/.mac-proxy/mac_proxy.py).
"""
import json
import os
import re
import sys

CMD = re.compile(r"(?:^|[;&|(`\n]|\$\()\s*(?:(?:sudo|env|exec|command|nohup|time|xargs)\s+(?:-\S+\s+)*)*"
                 r"(?:\w+=\S*\s+)*(?:\S*/)?(osascript|screencapture)(?=\s|$|[;&|)])")
HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?^\s*\2\s*$", re.S | re.M)   # heredoc bodies are data
DOWNLOADS = re.compile(r"(?:~|\$HOME|\$\{HOME\}|/Users/[^/\s]+)/Downloads(?:/|\s|$|[;&|)'\"])")
PROXY = os.environ.get("MAC_PROXY") or "~/.mac-proxy/mac_proxy.py"
REASON = """Do not run {tool} directly: macOS files the permission under Claude's version number, so it asks again after every update. Use the proxy (one grant, asked once):
  {p} applescript '...AppleScript...'      ('-' reads stdin)
  {p} jxa '...JXA...'
  {p} screenshot /absolute/path.png [screencapture options]
  {p} run COMMAND ARGS...                  (any other command that needs the proxy's grants)
  --timeout SECONDS goes before the verb; from Python use `from mac_proxy import call`."""
DL_REASON = """Do not read or write ~/Downloads directly: macOS files the permission under Claude's version number and asks again after every update. Use the proxy:
  {p} run /bin/ls -la ~/Downloads
  Python: from mac_proxy import call; call("run", argv=[...])"""


def decide(cmd):
    """Return a denial reason for a Bash command, or None."""
    body = HEREDOC.sub("", cmd)
    m = CMD.search(body)
    if m:
        return REASON.format(tool=m.group(1), p=PROXY)
    if DOWNLOADS.search(body) and "mac_proxy" not in body:
        return DL_REASON.format(p=PROXY)
    return None


def main():
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command") or ""
    except Exception:
        return            # never block over a parse problem
    reason = decide(cmd)
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}))


if __name__ == "__main__":
    main()
