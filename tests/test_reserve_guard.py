import io
import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guardrails"))
import reserve_guard as rg  # noqa: E402


def log_with(entries):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    return path


def iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t))


NOW = time.time()


def test_haiku_always_allowed():
    assert rg.delegate_first({"model": "haiku", "prompt": "x"}, NOW, log_with([])) is None


def test_recent_delegation_allows():
    p = log_with([{"ts": iso(NOW - 300), "exit": 0}])
    assert rg.delegate_first({"model": "sonnet", "prompt": "x"}, NOW, p) is None


def test_old_delegation_denied():
    p = log_with([{"ts": iso(NOW - 3600), "exit": 0}])
    assert "Delegate first" in rg.delegate_first({"model": "sonnet", "prompt": "x"}, NOW, p)


def test_reason_mark_allows():
    p = log_with([])
    assert rg.delegate_first({"model": "opus", "prompt": "task\nNO_DELEGATE: needs a browser"}, NOW, p) is None


def test_missing_log_never_blocks(tmp_path):
    assert rg.delegate_first({"model": "sonnet", "prompt": "x"}, NOW, str(tmp_path / "nope.jsonl")) is None


def run_hook(monkeypatch, capsys, tmp_path, event, quota=None, off=False):
    monkeypatch.setattr(rg, "HOME", str(tmp_path))
    if quota is not None:
        (tmp_path / "quota.json").write_text(json.dumps({"limits": quota}))
    if off:
        (tmp_path / "reserve-off").write_text("")
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    rg.main()
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"] if out else None


def test_agent_without_model_denied(monkeypatch, capsys, tmp_path):
    r = run_hook(monkeypatch, capsys, tmp_path, {"tool_name": "Agent", "tool_input": {"prompt": "x"}})
    assert r["permissionDecision"] == "deny" and "model" in r["permissionDecisionReason"]


def test_quota_cap_denies_heavy_tool(monkeypatch, capsys, tmp_path):
    q = {"at": time.time(), "five_hour": {"used_percentage": 96}}
    r = run_hook(monkeypatch, capsys, tmp_path, {"tool_name": "Bash", "tool_input": {}}, quota=q)
    assert r["permissionDecision"] == "deny" and "96%" in r["permissionDecisionReason"]


def test_agent_cap_is_lower(monkeypatch, capsys, tmp_path):
    q = {"at": time.time(), "five_hour": {"used_percentage": 91}}
    assert run_hook(monkeypatch, capsys, tmp_path, {"tool_name": "Bash", "tool_input": {}}, quota=q) is None
    r = run_hook(monkeypatch, capsys, tmp_path, {"tool_name": "Agent", "tool_input": {"model": "haiku"}}, quota=q)
    assert r["permissionDecision"] == "deny"


def test_read_tools_and_stale_snapshot_and_override(monkeypatch, capsys, tmp_path):
    q = {"at": time.time(), "five_hour": {"used_percentage": 99}}
    assert run_hook(monkeypatch, capsys, tmp_path, {"tool_name": "Read", "tool_input": {}}, quota=q) is None
    stale = {"at": time.time() - 3600, "five_hour": {"used_percentage": 99}}
    assert run_hook(monkeypatch, capsys, tmp_path, {"tool_name": "Bash", "tool_input": {}}, quota=stale) is None
    assert run_hook(monkeypatch, capsys, tmp_path, {"tool_name": "Bash", "tool_input": {}}, quota=q, off=True) is None
