import io
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guardrails"))
import bash_guard as bg  # noqa: E402


@pytest.mark.parametrize("cmd", [
    "osascript -e 'tell app \"Finder\" to activate'",
    "cd /tmp && osascript script.scpt",
    "sudo screencapture -x /tmp/a.png",
    "echo hi | xargs osascript",
    "FOO=1 /usr/bin/osascript -e x",
    "(screencapture a.png)",
])
def test_denies_direct_calls(cmd):
    assert bg.decide(cmd)


@pytest.mark.parametrize("cmd", [
    "grep osascript notes.md",
    "echo screencapture",
    "git log --oneline",
    "cat <<'EOF'\nosascript -e x\nEOF",
    "~/.mac-proxy/mac_proxy.py applescript 'tell app \"Finder\" to activate'",
])
def test_allows_mentions_and_proxy(cmd):
    assert bg.decide(cmd) is None


@pytest.mark.parametrize("cmd", ["ls ~/Downloads", "cp x $HOME/Downloads/", "cat /Us" + "ers/someone/Downloads/a.txt"])
def test_denies_downloads(cmd):
    assert "Downloads" in bg.decide(cmd)


def test_downloads_via_proxy_allowed():
    assert bg.decide("python3 mac_proxy.py run /bin/ls ~/Downloads") is None


def test_main_prints_deny(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_input": {"command": "osascript -e x"}})))
    bg.main()
    out = json.loads(capsys.readouterr().out)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"


def test_main_fails_open_on_bad_input(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    bg.main()
    assert capsys.readouterr().out == ""
