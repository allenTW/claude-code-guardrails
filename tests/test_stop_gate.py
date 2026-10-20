import io
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "guardrails"))
import stop_gate as sg  # noqa: E402


def _transcript(tmp_path, entries):
    p = tmp_path / "t.jsonl"
    p.write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in entries), encoding="utf-8")
    return str(p)


def _assistant(cwd, *blocks):
    return {"type": "assistant", "cwd": cwd, "message": {"content": list(blocks)}}


def _bash(cmd):
    return {"type": "tool_use", "name": "Bash", "input": {"command": cmd}}


def test_bash_targets_redirect_sed_tee_cp(tmp_path):
    files, commits = sg.bash_targets(
        "cd sub && echo hi > a.txt; sed -i '' 's/x/y/' b.py | tee -a c.log; cp x.py /abs/d.py; ls 2>&1",
        str(tmp_path))
    sub = str(tmp_path / "sub")
    assert {sub + "/a.txt", sub + "/b.py", sub + "/c.log", "/abs/d.py"} == files
    assert commits == set()


def test_bash_targets_git_commit_repo():
    _, commits = sg.bash_targets('git -C "/r/one" commit -m x && cd /r/two && git commit -m y', "/w")
    assert commits == {"/r/one", "/r/two"}


def test_lazy_hits_english():
    text = ("Not done\n- I did not run the tests.\n- The change is not committed.\n"
            "- It has not been pushed.\nWant me to continue?")
    assert sg.lazy_hits(text) == ["tests not run", "not committed", "not pushed", "asks whether to continue"]
    assert sg.lazy_hits("- rm was denied, please delete it yourself.") == ["hands doable work to the user"]


def test_lazy_hits_chinese():
    text = "**未做**\n- 我沒有跑 `test_a.py`。\n- 我沒有 commit。\n- 那個 commit 還沒 push。\n要我接著做哪個？"
    assert sg.lazy_hits(text) == ["沒跑測試", "沒 commit", "沒 push", "結尾問要不要繼續"]


def test_lazy_hits_keeps_real_blockers():
    text = ("- Publishing to the blog is a public release, so it was not pushed.\n"
            "- No API key is available, tests that need credentials were not run.\n"
            "- 有臉書發文，屬於對外發佈，沒重啟也沒按。\n- Already committed and pushed.")
    assert sg.lazy_hits(text) == []


def test_lazy_hits_only_reads_not_done_column_and_skips_quotes():
    text = ("Reason\n- The three-column report was abused: 「not committed, please delete it yourself」 went into the not-done column.\n\n"
            "Verified\n- tests pass.\n\n"
            "Not done\n- The new hook has not fired in a real session yet.\n\n"
            "Why\n- whatever")
    assert sg.lazy_hits(text) == []
    assert sg.lazy_hits(text.replace("has not fired in a real session yet", "is not committed")) == ["not committed"]


def test_checklist_open(tmp_path):
    (tmp_path / "s1.md").write_text("- [x] done\n- [ ] run tests\n- [ ] commit\n", encoding="utf-8")
    assert sg.checklist_open("s1", str(tmp_path)) == ["run tests", "commit"]
    assert sg.checklist_open("nope", str(tmp_path)) == []


def test_parse_transcript_last_text_is_final_turn(tmp_path):
    tp = _transcript(tmp_path, [
        _assistant("/w", {"type": "text", "text": "old report: not committed"}),
        {"type": "user", "message": {"content": "continue"}},
        _assistant("/w", {"type": "text", "text": "all done"}, _bash("echo x > out.md")),
    ])
    info = sg.parse_transcript(tp)
    assert info["last_text"] == "all done"
    assert info["files"] == {"/w/out.md"}


def test_evaluate_blocks_dirty_bash_edit_but_not_other_sessions_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sg, "SKIP_PATH_PARTS", ())  # pytest tmp_path may live under /tmp/
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "mine.py").write_text("x", encoding="utf-8")
    (repo / "theirs.py").write_text("y", encoding="utf-8")
    tp = _transcript(tmp_path, [_assistant(str(repo), _bash("echo x > mine.py"),
                                           {"type": "text", "text": "verified"})])
    problems, _ = sg.evaluate({"transcript_path": tp, "session_id": "s"}, str(tmp_path))
    assert len(problems) == 1 and "mine.py" in problems[0] and "theirs.py" not in problems[0]


def test_evaluate_prefers_stdin_last_message(tmp_path):
    tp = _transcript(tmp_path, [_assistant("/w", {"type": "text", "text": "all done"})])
    problems, had = sg.evaluate({"transcript_path": tp, "last_assistant_message": "I have not committed."},
                                str(tmp_path))
    assert had and problems == ["the report lists doable work as not done: not committed"]


def test_evaluate_flags_unpushed_commit(tmp_path):
    upstream = tmp_path / "up.git"
    subprocess.run(["git", "init", "-q", "--bare", str(upstream)], check=True)
    repo = tmp_path / "r"
    subprocess.run(["git", "clone", "-q", str(upstream), str(repo)], check=True, capture_output=True)
    env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t",
               GIT_COMMITTER_EMAIL="t@e")
    (repo / "f").write_text("1")
    subprocess.run(["git", "-C", str(repo), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "one"], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "push", "-q", "-u", "origin", "HEAD"], check=True, capture_output=True)
    (repo / "f").write_text("2")
    subprocess.run(["git", "-C", str(repo), "commit", "-qam", "two"], check=True, env=env)
    tp = _transcript(tmp_path, [_assistant(str(repo), _bash("git commit -qam two"),
                                           {"type": "text", "text": "done"})])
    problems, _ = sg.evaluate({"transcript_path": tp, "session_id": "s"}, str(tmp_path))
    assert any("not pushed" in p and "(1 commits)" in p for p in problems)


def test_main_skips_when_stop_hook_active(monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"stop_hook_active": True})))
    sg.main()
    assert capsys.readouterr().out == ""


def test_main_blocks_with_reason(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(sg, "LOG_PATH", str(tmp_path / "log.jsonl"))
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"last_assistant_message": "Not done\n- not committed"})))
    sg.main()
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block" and "not committed" in out["reason"]
