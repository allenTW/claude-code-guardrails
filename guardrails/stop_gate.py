#!/usr/bin/env python3
"""Stop hook: block the first stop when this session is about to report work it could still finish.

Checks, all scoped to what THIS session touched (other sessions may edit the same repo):
  1. open todos (TodoWrite, or a checklist file <GUARDRAILS_HOME>/todo/<session_id>.md with "- [ ]" lines)
  2. files this session wrote (Edit/Write and Bash: > / >> / tee / sed -i / cp / mv) still dirty in git
  3. repos this session committed in that still have unpushed commits
  4. the final report lists doable work as "not done" (no tests run, no commit/push, no restart,
     not checked, "want me to continue?", "please run it yourself")
Blocks at most once per stop (stop_hook_active guard) so it can never loop. Fails open on any error.
Reports are matched in English and Traditional Chinese; add your own patterns to LAZY.
"""
import json, os, re, shlex, subprocess, sys

HOME = os.path.expanduser("~")
GHOME = os.environ.get("GUARDRAILS_HOME") or os.path.join(HOME, ".claude-guardrails")
TODO_DIR = os.path.join(GHOME, "todo")
LOG_PATH = os.path.join(GHOME, "logs", "stop_gate.jsonl")

# Phrases that put doable work into the "not done" column.
LAZY = [
    (r"\b(did not|didn't|haven't|have not|not yet|never)\s+(run|ran)\s+(the\s+)?(unit\s+)?(tests?|pytest)\b|tests?\s+(were|was)\s+not\s+run", "tests not run"),
    (r"\b(not|n't|haven't|hasn't)\s+(yet\s+)?(been\s+)?commit(ted)?\b|\bnot committed\b", "not committed"),
    (r"\b(not|n't|haven't|hasn't)\s+(yet\s+)?(been\s+)?pushed\b|\bnot pushed\b", "not pushed"),
    (r"\b(not|n't)\s+(yet\s+)?(been\s+)?(restarted|verified in|checked in|tested in)\b", "not restarted or checked"),
    (r"\b(want|would you like) me to (continue|keep going|go on|proceed)\b|\bshall I (continue|proceed)\b", "asks whether to continue"),
    (r"\b(please|you (need|have) to|you should)\s+(manually\s+)?(run|delete|restart|paste|execute)\b", "hands doable work to the user"),
    (r"(沒|未|還沒|尚未)(有)?(再)?跑\s*(過)?\s*`?(單元)?(測試|pytest|test)|測試(還)?(沒|未)跑", "沒跑測試"),
    (r"(沒|未|還沒|尚未)(有)?\s*commit|commit\s*(還沒|尚未)", "沒 commit"),
    (r"(沒|未|還沒|尚未)(有)?\s*push|push\s*(還沒|尚未)", "沒 push"),
    (r"(沒|未|還沒|尚未)(有)?(再)?重啟", "沒重啟"),
    (r"(沒|未|還沒|尚未)(有)?(用|在)?(瀏覽器|實際|實機|親自)?(上)?(看過|看(?!到|起來|不)|開過|打開|測過|實測|確認畫面)", "沒實際看或測"),
    (r"(沒|未)(有)?(做)?(瀏覽器|實機|實際)(實測|測試|確認)", "沒實際看或測"),
    (r"要(不要)?我(接著|繼續|再)", "結尾問要不要繼續"),
    (r"(需要|請|麻煩)你(自己|手動)?(刪|執行|跑|貼|重啟|關掉)", "把能自動化的事丟給使用者"),
]
# Lines naming a genuine blocker stay in the "not done" column.
EXEMPT = re.compile(
    r"publish|public release|payment|credentials?|api key|password|no hardware|cannot hear|quota|already committed|already pushed|"
    r"對外|發佈|發布|公開|發文|臉書|碰錢|交易|下單|金鑰|密碼|聽不到|聽不見|無法聽|沒有硬體|沒有實機|"
    r"不在\s*repo|不屬於這個\s*repo|沒有\s*git|不是\s*git|額度|配額|quota|已\s*commit|已\s*push|"
    r"算圖中|審片(可能)?正在|正在跑|別的對話|其他對話")
# Lines describing what the user should verify, not something Claude skipped.
FIELD = re.compile(r"不用|不需要|無須|無需|no need to|not required|nothing to")

# files whose path contains one of these are scratch space and never count as unfinished work
SKIP_PATH_PARTS = ("/tmp/", "scratchpad")
WRITE_CMDS = ("cp", "mv", "install", "rsync")


def _abs(p, cwd):
    p = os.path.expanduser(p.strip("'\""))
    if not p or p.startswith("-") or p.startswith("/dev/"):
        return None
    return os.path.normpath(p if os.path.isabs(p) else os.path.join(cwd or "/", p))


def bash_targets(cmd, cwd):
    """Best-effort list of files a Bash command writes, plus repos it commits in."""
    files, commits = set(), set()
    for seg in re.split(r"&&|\|\||;|\n|\|", cmd):
        seg = seg.strip()
        m = re.match(r"cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*$", seg)
        if m:
            cwd = _abs(m.group(1), cwd) or cwd
            continue
        for m in re.finditer(r"(?<![0-9&<])>{1,2}\s*(\"[^\"]+\"|'[^']+'|[^\s|;&<>]+)", seg):
            files.add(_abs(m.group(1), cwd))
        try:
            toks = shlex.split(seg, comments=False)
        except ValueError:
            toks = seg.split()
        toks = [t for t in toks if t]
        if not toks:
            continue
        if toks[0] == "tee":
            files.update(_abs(t, cwd) for t in toks[1:] if not t.startswith("-"))
        elif toks[0] == "sed" and any(t.startswith("-i") for t in toks[1:]):
            files.add(_abs(toks[-1], cwd))
        elif toks[0] in WRITE_CMDS and len(toks) >= 3:
            files.add(_abs(toks[-1], cwd))
        if toks[0] == "git" and "commit" in toks:
            repo = cwd
            if "-C" in toks:
                i = toks.index("-C")
                if i + 1 < len(toks):
                    repo = _abs(toks[i + 1], cwd) or cwd
            if repo:
                commits.add(repo)
    files.discard(None)
    return files, commits


def parse_transcript(path):
    """Collect todos, written files, committed repos and the last assistant text of the final turn."""
    out = {"todos": [], "files": set(), "commits": set(), "last_text": ""}
    turn_texts = []
    with open(path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("isSidechain"):
                continue
            msg = e.get("message") or {}
            c = msg.get("content")
            if e.get("type") == "user" and isinstance(c, str) and not e.get("isMeta"):
                turn_texts = []
            if e.get("type") != "assistant" or not isinstance(c, list):
                continue
            cwd = e.get("cwd") or ""
            for b in c:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    turn_texts.append(b["text"])
                if b.get("type") != "tool_use":
                    continue
                inp = b.get("input") or {}
                name = b.get("name")
                if name == "TodoWrite":
                    out["todos"] = inp.get("todos") or []
                elif name in ("Edit", "Write", "NotebookEdit") and (inp.get("file_path") or inp.get("notebook_path")):
                    out["files"].add(_abs(inp.get("file_path") or inp.get("notebook_path"), cwd))
                elif name in ("Bash", "bash") and isinstance(inp.get("command"), str):
                    fs, cs = bash_targets(inp["command"], cwd)
                    out["files"] |= fs
                    out["commits"] |= cs
    out["files"].discard(None)
    out["last_text"] = turn_texts[-1] if turn_texts else ""
    return out


NOT_DONE_HEAD = re.compile(r"^\W*(not done|couldn't do|could not do|未做|沒做完|做不到)", re.I)
OTHER_HEAD = re.compile(r"^\W*(verified|done|delegated|needs your decision|why|reason|已驗證|已完成|已派出|待你決定|待決|為什麼|原因)", re.I)


def not_done_part(text):
    """The "not done" column if the report has one (plus the closing lines), else the whole text.

    Quoted examples inside 「」 are dropped so explaining a phrase is not mistaken for using it."""
    text = re.sub(r"「[^」\n]*」", "", text or "")
    lines = text.split("\n")
    start = next((i for i, l in enumerate(lines) if NOT_DONE_HEAD.match(l)), None)
    if start is None:
        return text
    part = []
    for l in lines[start:]:
        if part and OTHER_HEAD.match(l):
            break
        part.append(l)
    return "\n".join(part + lines[-2:])


def lazy_hits(text):
    """Return labels of doable-work phrases in the report, skipping lines that name a real blocker."""
    hits = []
    for line in re.split(r"[\n。；]", not_done_part(text)):
        if not line.strip() or EXEMPT.search(line) or FIELD.search(line):
            continue
        for pat, label in LAZY:
            if re.search(pat, line, re.I) and label not in hits:
                hits.append(label)
    return hits


def checklist_open(session_id, todo_dir=TODO_DIR):
    if not session_id:
        return []
    p = os.path.join(todo_dir, session_id + ".md")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8", errors="ignore") as f:
        return [l.strip()[5:].strip() for l in f if l.strip().startswith("- [ ]")]


def _git(args, cwd):
    return subprocess.run(["git", "-C", cwd] + args, capture_output=True, text=True, timeout=5)


def dirty_files(paths):
    dirty = []
    for p in sorted(paths):
        d = os.path.dirname(p)
        if not os.path.isdir(d) or any(part in p for part in SKIP_PATH_PARTS):
            continue
        try:
            r = _git(["status", "--porcelain", "--", p], d)
            if r.returncode == 0 and r.stdout.strip():
                dirty.append(p)
        except Exception:
            pass
    return dirty


def unpushed_repos(repos):
    out = []
    for r in sorted(repos):
        if not os.path.isdir(r):
            continue
        try:
            top = _git(["rev-parse", "--show-toplevel"], r)
            if top.returncode != 0:
                continue
            res = _git(["rev-list", "--count", "@{u}..HEAD"], top.stdout.strip())
            if res.returncode == 0 and res.stdout.strip().isdigit() and int(res.stdout.strip()) > 0:
                out.append("%s (%s commits)" % (top.stdout.strip(), res.stdout.strip()))
        except Exception:
            pass
    return sorted(set(out))


def evaluate(d, todo_dir=TODO_DIR):
    tp = d.get("transcript_path")
    info = parse_transcript(tp) if tp and os.path.exists(tp) else {"todos": [], "files": set(), "commits": set(), "last_text": ""}
    last = d.get("last_assistant_message") or info["last_text"]
    problems = []
    open_t = [t.get("content", "?") for t in info["todos"] if t.get("status") != "completed"]
    open_t += checklist_open(d.get("session_id"), todo_dir)
    if open_t:
        problems.append("unfinished checklist items: " + "; ".join(open_t[:8]))
    dirty = dirty_files(info["files"])
    if dirty:
        problems.append("files this session wrote that are still uncommitted: " + "; ".join(dirty[:8]))
    unp = unpushed_repos(info["commits"])
    if unp:
        problems.append("committed but not pushed: " + "; ".join(unp))
    hits = lazy_hits(last)
    if hits:
        problems.append("the report lists doable work as not done: " + ", ".join(hits))
    return problems, bool(d.get("last_assistant_message"))


def log(rec, path=LOG_PATH):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def main():
    d = json.load(sys.stdin)
    if d.get("stop_hook_active"):
        return
    problems, had_last = evaluate(d)
    log({"session": d.get("session_id"), "keys": sorted(d.keys()), "stdin_last": had_last,
         "blocked": bool(problems), "problems": problems})
    if problems:
        print(json.dumps({"decision": "block", "reason":
            "Self-check before reporting failed: " + " / ".join(problems) +
            ". In order: (1) do what you can do now (run the tests, commit, push, restart, look at the page); "
            "(2) if a permission blocks it, say exactly which one; "
            "(3) only a real blocker (publishing, money, credentials, missing hardware) may stay in the 'not done' column, "
            "with what is blocking it."}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
