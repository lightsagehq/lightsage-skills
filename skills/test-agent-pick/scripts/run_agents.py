#!/usr/bin/env python3
"""Run a task file N times on local coding-agent CLIs, each run in a clean, isolated workspace.

Usage:
  python3 run_agents.py --init tasks.json                 # write a task-file template
  python3 run_agents.py tasks.json --dry-run              # print the plan and session count, run nothing
  python3 run_agents.py tasks.json --yes                  # run it (resumes: finished runs are skipped)

Options:
  --agents claude,codex      agents to use (default: every supported CLI found on PATH)
  --runs 3                   runs per task per agent (3 minimum, 5+ before a decision)
  --timeout 600              seconds per session before it is killed and recorded as a stall
  --concurrency 2            sessions at once
  --out DIR                  results folder (default: ./agent-pick-<date>)
  --only ID[,ID]             run only these task ids (for a smoke test)
  --claude PATH / --codex PATH          binaries to use
  --claude-model M / --codex-model M    pin a model (default: the CLI's own default)
  --shell                    let Claude run any shell command (default: package installs and curl only)
  --keep-api-keys            keep ANTHROPIC_API_KEY / OPENAI_API_KEY in the agents' environment
  --custom NAME=CMD          extra agent: CMD runs in the workspace with the prompt on stdin;
                             its stdout is the transcript (repeatable)

Isolation per run: a fresh temp workspace (empty, or a copy of the task's fixture repo), a temp HOME,
no user/project settings, no CLAUDE.md/AGENTS.md, no MCP servers, plugins, skills, memories or apps.
Claude keeps the real HOME only for its login (macOS keychain); everything else it would read is off.

Output per run: OUT/runs/<agent>/<task>/r<k>/{meta.json, answer.md, events.jsonl, diff.txt}
Next step: python3 tally.py OUT --sheet, judge, then python3 tally.py OUT
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import difflib
import json
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build", ".turbo", "target", ".cache"}
LOCKFILES = {"package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lockb", "bun.lock", "poetry.lock", "uv.lock", "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock"}
INSTALL_RE = re.compile(
    r"\b(npm (?:i|install|add)|pnpm (?:add|i|install)|yarn add|bun (?:add|i|install)|npx [\w@./-]+|"
    r"pip3? install|uv (?:add|pip install)|poetry add|go get|go install|cargo add|cargo install|"
    r"gem install|bundle add|composer require|dotnet add package|brew install)\b[^\n;&|]*")
URL_RE = re.compile(r"https?://[^\s\"'<>)\]}`]+")
KEY_ENV = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CODEX_API_KEY", "ANTHROPIC_AUTH_TOKEN")
CLAUDE_ALLOWED = ["Read", "Edit", "Write", "Glob", "Grep", "WebFetch", "WebSearch", "TodoWrite"] + [
    f"Bash({p}:*)" for p in (
        "npm install", "npm i", "npm add", "pnpm add", "yarn add", "bun add", "pip install", "pip3 install",
        "uv add", "uv pip install", "poetry add", "go get", "cargo add", "gem install", "bundle add",
        "composer require", "curl", "ls", "cat")]

TEMPLATE = {
    "category": "transactional email API",
    "brand": {"name": "YourBrand", "domains": ["yourbrand.com"], "packages": ["yourbrand"], "aliases": []},
    "competitors": [
        {"name": "Competitor A", "domains": ["competitor-a.com"], "packages": ["competitor-a"], "aliases": []},
        {"name": "Competitor B", "domains": ["competitor-b.io"], "packages": ["@competitor-b/sdk"], "aliases": []},
    ],
    "tasks": [
        {"id": "ask-01", "kind": "ask", "prompt": "Which email API should I use to send password reset emails from a Next.js app? Pick one and say why."},
        {"id": "build-01", "kind": "build", "prompt": "Add a password reset email to this app.", "repo": "fixtures/nextjs-app"},
    ],
}


def die(msg):
    sys.exit(f"error: {msg}")


def load_tasks(path):
    p = Path(path)
    try:
        spec = json.loads(p.read_text())
    except (OSError, ValueError) as e:
        die(f"cannot read {p}: {e}")
    for key in ("brand", "tasks"):
        if key not in spec:
            die(f"{p} has no '{key}' (see --init)")
    ids = set()
    for t in spec["tasks"]:
        if not t.get("id") or not t.get("prompt"):
            die(f"every task needs an id and a prompt: {t}")
        if t["id"] in ids:
            die(f"duplicate task id {t['id']}")
        ids.add(t["id"])
        t.setdefault("kind", "ask")
        if t.get("repo"):
            repo = (p.parent / t["repo"]).resolve()
            if not repo.is_dir():
                die(f"task {t['id']}: fixture repo {repo} does not exist")
            t["_repo"] = str(repo)
    return spec


def which(name, override):
    if override:
        path = os.path.expanduser(override)
        if not os.access(path, os.X_OK):
            die(f"{path} is not executable")
        return path
    return shutil.which(name)


def version(binary):
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)
        return (out.stdout or out.stderr).strip().splitlines()[0]
    except Exception:  # noqa: BLE001 - any failure just means "unknown"
        return "unknown"


def claude_flags(binary):
    try:
        help_text = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL).stdout
    except Exception:  # noqa: BLE001
        help_text = ""
    return {f: (f in help_text) for f in ("--safe-mode", "--no-session-persistence", "--disable-slash-commands", "--setting-sources", "--strict-mcp-config")}


def build_agents(a):
    agents = {}
    wanted = [x.strip() for x in a.agents.split(",")] if a.agents else ["claude", "codex"]
    for name in wanted:
        if name == "claude":
            b = which("claude", a.claude)
            if b:
                agents["claude"] = {"bin": b, "version": version(b), "flags": claude_flags(b)}
            elif a.agents:
                die("claude not found; pass --claude PATH")
        elif name == "codex":
            b = which("codex", a.codex)
            if b:
                agents["codex"] = {"bin": b, "version": version(b)}
            elif a.agents:
                die("codex not found; pass --codex PATH")
        elif name not in dict(c.split("=", 1) for c in a.custom):
            die(f"unknown agent {name}: use claude, codex or --custom {name}=CMD")
    for spec in a.custom:
        if "=" not in spec:
            die("--custom takes NAME=CMD")
        n, cmd = spec.split("=", 1)
        agents[n] = {"cmd": cmd, "version": "custom"}
    if not agents:
        die("no agent CLI found. Install Claude Code or Codex, or pass --custom NAME=CMD")
    return agents


def claude_cmd(a, info, prompt):
    f = info["flags"]
    cmd = [info["bin"], "-p", prompt, "--output-format", "stream-json", "--verbose"]
    if f.get("--safe-mode"):
        cmd.append("--safe-mode")
    if f.get("--setting-sources"):
        cmd += ["--setting-sources", ""]
    if f.get("--strict-mcp-config"):
        cmd.append("--strict-mcp-config")
    if f.get("--disable-slash-commands"):
        cmd.append("--disable-slash-commands")
    if f.get("--no-session-persistence"):
        cmd.append("--no-session-persistence")
    if a.shell:
        cmd += ["--permission-mode", "bypassPermissions"]
    else:
        cmd += ["--permission-mode", "acceptEdits", "--allowedTools", *CLAUDE_ALLOWED]
    if a.claude_model:
        cmd += ["--model", a.claude_model]
    return cmd


def codex_cmd(a, info, prompt, work):
    cmd = [info["bin"], "exec", "--json", "--skip-git-repo-check", "--ephemeral", "-C", str(work),
           "-s", "workspace-write", "-c", "sandbox_workspace_write.network_access=true"]
    for feat in ("apps", "plugins", "memories", "hooks", "browser_use", "computer_use"):
        cmd += ["-c", f"features.{feat}=false"]
    if a.codex_model:
        cmd += ["-m", a.codex_model]
    return cmd + [prompt]


def base_env(a, home):
    env = {k: v for k, v in os.environ.items()
           if not (k.startswith("CLAUDECODE") or k in ("CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_SSE_PORT", "AGENTS_HOME"))}
    if not a.keep_api_keys:
        for k in KEY_ENV:
            env.pop(k, None)
    env["TMPDIR"] = str(home.parent)
    return env


def copy_fixture(src, dst):
    if src:
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(*SKIP_DIRS), symlinks=True, dirs_exist_ok=True)
    else:
        dst.mkdir(parents=True, exist_ok=True)


def text_files(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            rel = str(p.relative_to(root))
            try:
                if p.is_symlink() or p.stat().st_size > 200_000:
                    continue
                out[rel] = p.read_text()
            except (UnicodeDecodeError, OSError):
                continue
    return out


def workspace_diff(before, after):
    chunks = []
    for rel in sorted(set(before) | set(after)):
        if Path(rel).name in LOCKFILES:
            if rel not in before:
                chunks.append(f"+++ {rel} (lockfile created)\n")
            continue
        old, new = before.get(rel, ""), after.get(rel, "")
        if old != new:
            chunks.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{rel}", f"b/{rel}", n=1))
    text = "".join(chunks)
    return text[:300_000]


def walk_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)


def parse_claude(lines):
    r = {"answer": "", "searches": [], "fetched": [], "fetch_errors": [], "commands": [], "denied": [], "error": None, "turns": None}
    pending = {}
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type")
        content = (ev.get("message") or {}).get("content") or []
        if t == "assistant" and isinstance(content, list):
            for c in content:
                if c.get("type") != "tool_use":
                    continue
                name, inp = c.get("name", ""), c.get("input") or {}
                pending[c.get("id")] = (name, inp)
                if name == "WebSearch":
                    r["searches"].append(inp.get("query", ""))
                elif name == "WebFetch":
                    r["fetched"].append(inp.get("url", ""))
                elif name == "Bash":
                    cmd = inp.get("command", "")
                    r["commands"].append(cmd[:400])
                    if re.search(r"\b(curl|wget|http)\b", cmd):
                        r["fetched"].extend(URL_RE.findall(cmd))
                elif "fetch" in (name + str(inp.get("subagent_type", ""))).lower():
                    # fetch tools under other names, or a fetch subagent briefed with the URLs to read
                    r["fetched"].extend(u for s in walk_strings(inp) for u in URL_RE.findall(s))
        elif t == "user" and isinstance(content, list):
            for c in content:
                if c.get("type") != "tool_result":
                    continue
                name, inp = pending.get(c.get("tool_use_id"), ("", {}))
                body = " ".join(walk_strings(c.get("content")))[:600]
                if name == "WebFetch" and (c.get("is_error") or re.search(r"\b(40[0-9]|41[0-9]|429|5\d\d)\b.{0,40}(status|error|forbidden|not found)|status code (4|5)\d\d", body, re.I)):
                    r["fetch_errors"].append({"url": inp.get("url", ""), "error": body[:200]})
        elif t == "result":
            r["answer"] = ev.get("result") or ""
            r["turns"] = ev.get("num_turns")
            if ev.get("is_error"):
                r["error"] = (ev.get("result") or ev.get("subtype") or "error")[:400]
            for d in ev.get("permission_denials") or []:
                r["denied"].append(f"{d.get('tool_name')}: {json.dumps(d.get('tool_input'))[:200]}")
    return r


def parse_codex(lines):
    r = {"answer": "", "searches": [], "fetched": [], "fetch_errors": [], "commands": [], "denied": [], "error": None, "turns": None}
    messages = []
    for line in lines:
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        t = ev.get("type", "")
        item = ev.get("item") or {}
        it = item.get("type")
        if t == "item.completed" and it == "agent_message":
            messages.append(item.get("text") or "")
        elif t == "item.completed" and it == "web_search":
            q = item.get("query") or (item.get("action") or {}).get("query") or ""
            if q:
                r["searches"].append(q)
            url = (item.get("action") or {}).get("url")
            if url:
                r["fetched"].append(url)
        elif t == "item.completed" and it == "command_execution":
            cmd = item.get("command") or ""
            r["commands"].append(cmd[:400])
            if re.search(r"\b(curl|wget)\b", cmd):
                urls = URL_RE.findall(cmd)
                r["fetched"].extend(urls)
                out = (item.get("aggregated_output") or "")[:2000]
                if item.get("exit_code") not in (0, None) or re.search(r"\b(403|404|429|5\d\d)\b", out[:300]):
                    for u in urls:
                        r["fetch_errors"].append({"url": u, "error": f"exit {item.get('exit_code')}: {out[:160]}"})
        elif t in ("error", "turn.failed"):
            r["error"] = json.dumps(ev)[:400]
    r["answer"] = messages[-1] if messages else ""
    return r


def parse_custom(lines):
    text = "".join(lines)
    return {"answer": text[-20_000:], "searches": [], "fetched": sorted(set(URL_RE.findall(text))), "fetch_errors": [],
            "commands": [], "denied": [], "error": None, "turns": None}


def kill_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        proc.kill()


def run_one(a, spec, agent, info, task, k, out_root, lock):
    run_dir = out_root / "runs" / agent / task["id"] / f"r{k}"
    meta_path = run_dir / "meta.json"
    if meta_path.exists():
        try:
            if json.loads(meta_path.read_text()).get("status") in ("ok", "empty"):
                return "skipped"
        except ValueError:
            pass
    run_dir.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix="agent-pick-"))
    home, work = root / "home", root / "work"
    home.mkdir()
    copy_fixture(task.get("_repo"), work)
    if task.get("_repo") and not (work / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=work, capture_output=True)
    before = text_files(work)
    env = base_env(a, home)
    prompt = task["prompt"]
    if agent == "claude":
        cmd = claude_cmd(a, info, prompt)
        env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
        env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
        stdin_data = None
    elif agent == "codex":
        cmd = codex_cmd(a, info, prompt, work)
        codex_home = root / "codex-home"
        codex_home.mkdir()
        real_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
        if (real_home / "auth.json").exists():
            os.symlink(real_home / "auth.json", codex_home / "auth.json")  # symlink, not copy: token refreshes must reach the real login
        (codex_home / "config.toml").write_text("")
        env.update(HOME=str(home), CODEX_HOME=str(codex_home))
        stdin_data = None
    else:
        cmd = ["/bin/sh", "-c", info["cmd"]]
        env["HOME"] = str(home)
        stdin_data = prompt
    t0 = time.time()
    status, raw = "ok", ""
    proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL, start_new_session=True)
    try:
        raw, _ = proc.communicate(stdin_data, timeout=a.timeout)
    except subprocess.TimeoutExpired:
        kill_group(proc)
        raw, _ = proc.communicate()
        status = "timeout"
    secs = round(time.time() - t0)
    lines = (raw or "").splitlines()
    parsed = {"claude": parse_claude, "codex": parse_codex}.get(agent, parse_custom)(lines)
    after = text_files(work)
    diff = workspace_diff(before, after)
    installs = sorted({m.group(0).strip()[:200] for c in parsed["commands"] for m in INSTALL_RE.finditer(c)})
    if status == "ok" and parsed["error"]:
        status = "error"
    if status == "ok" and not parsed["answer"].strip() and not diff:
        status = "empty"
    meta = {
        "agent": agent, "agent_version": info["version"], "task_id": task["id"], "kind": task.get("kind"),
        "run": k, "prompt": prompt, "status": status, "exit_code": proc.returncode, "secs": secs,
        "turns": parsed["turns"], "searches": parsed["searches"], "fetched": sorted(set(u for u in parsed["fetched"] if u)),
        "fetch_errors": parsed["fetch_errors"], "commands": parsed["commands"][:60], "installs": installs,
        "denied": parsed["denied"], "files_changed": sorted(r for r in set(before) | set(after) if before.get(r) != after.get(r)),
        "error": parsed["error"], "started": dt.datetime.fromtimestamp(t0).isoformat(timespec="seconds"),
    }
    (run_dir / "events.jsonl").write_text(raw or "")
    (run_dir / "answer.md").write_text(parsed["answer"])
    (run_dir / "diff.txt").write_text(diff)
    meta_path.write_text(json.dumps(meta, indent=2))
    shutil.rmtree(root, ignore_errors=True)
    with lock:
        print(f"[{status:7}] {agent:8} {task['id']:12} r{k}  {secs:4}s  fetched {len(meta['fetched'])}  installs {len(installs)}", flush=True)
    return status


def plan(a, spec, agents, tasks):
    n = len(tasks) * a.runs * len(agents)
    kinds = {}
    for t in tasks:
        kinds[t["kind"]] = kinds.get(t["kind"], 0) + 1
    lo, hi = n * 1 / max(1, a.concurrency), n * 5 / max(1, a.concurrency)  # minutes: 1-5 per session
    print("Plan")
    print(f"  category     {spec.get('category', '-')}")
    print(f"  brand        {spec['brand']['name']}   competitors: {', '.join(c['name'] for c in spec.get('competitors', [])) or '-'}")
    print(f"  tasks        {len(tasks)} ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))})")
    print(f"  runs         {a.runs} per task per agent")
    for name, info in agents.items():
        print(f"  agent        {name:8} {info['version']}")
    print(f"  SESSIONS     {n}  = {len(tasks)} tasks x {a.runs} runs x {len(agents)} agents")
    print(f"  time         about {lo:.0f}-{hi:.0f} min at concurrency {a.concurrency} (timeout {a.timeout}s per session)")
    print(f"  usage        each session is a full agent run on your own Claude/Codex login or plan")
    print(f"  isolation    temp workspace per run (codex/custom also get a temp HOME); no user config, CLAUDE.md/AGENTS.md, MCP, plugins, skills, memories")
    print(f"  claude shell {'any command (--shell)' if a.shell else 'package installs and curl only'}")
    print(f"  api keys     {'kept' if a.keep_api_keys else 'ANTHROPIC_API_KEY/OPENAI_API_KEY removed (pass --keep-api-keys to use them)'}")
    print(f"  output       {a.out}")
    if a.runs < 3:
        print("  WARNING      fewer than 3 runs per task: rates will not mean much")
    if "claude" in agents and not agents["claude"]["flags"].get("--safe-mode"):
        print("  note         this Claude Code has no --safe-mode; isolation relies on --setting-sources/--strict-mcp-config")
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("tasks", nargs="?")
    ap.add_argument("--init", metavar="PATH")
    ap.add_argument("--agents")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--out")
    ap.add_argument("--only")
    ap.add_argument("--claude")
    ap.add_argument("--codex")
    ap.add_argument("--claude-model")
    ap.add_argument("--codex-model")
    ap.add_argument("--shell", action="store_true")
    ap.add_argument("--keep-api-keys", action="store_true")
    ap.add_argument("--custom", action="append", default=[])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="actually run (after the user approved the dry-run plan)")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()

    if a.init:
        p = Path(a.init)
        if p.exists():
            die(f"{p} exists")
        p.write_text(json.dumps(TEMPLATE, indent=2) + "\n")
        print(f"wrote {p}; replace the brand, competitors and tasks")
        return
    if not a.tasks:
        ap.error("give a task file, or --init PATH")
    spec = load_tasks(a.tasks)
    tasks = spec["tasks"]
    if a.only:
        keep = set(a.only.split(","))
        tasks = [t for t in tasks if t["id"] in keep]
        if not tasks:
            die(f"--only matched no task ids: {a.only}")
    a.out = Path(a.out or f"agent-pick-{dt.date.today().isoformat()}").resolve()
    agents = build_agents(a)
    n = plan(a, spec, agents, tasks)
    if a.dry_run or not a.yes:
        print("\nDry run: nothing was started. Show this plan to the user; rerun with --yes once they agree.")
        return
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "tasks.json").write_text(json.dumps(spec, indent=2, default=str))
    (a.out / "plan.json").write_text(json.dumps({
        "agents": {k: {"version": v["version"]} for k, v in agents.items()}, "runs": a.runs, "sessions": n,
        "tasks": [t["id"] for t in tasks], "shell": a.shell, "started": dt.datetime.now().isoformat(timespec="seconds")}, indent=2))
    jobs = [(ag, t, k) for ag in agents for t in tasks for k in range(1, a.runs + 1)]
    random.Random(a.seed).shuffle(jobs)  # interleave agents and tasks so time-of-day drift doesn't line up with one of them
    lock = threading.Lock()
    counts = {}
    with cf.ThreadPoolExecutor(max_workers=max(1, a.concurrency)) as ex:
        futs = [ex.submit(run_one, a, spec, ag, agents[ag], t, k, a.out, lock) for ag, t, k in jobs]
        for f in cf.as_completed(futs):
            try:
                s = f.result()
            except Exception as e:  # noqa: BLE001 - one broken run must not stop the batch
                s = "crashed"
                print(f"run crashed: {e}", file=sys.stderr)
            counts[s] = counts.get(s, 0) + 1
    print("\nDone: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    print(f"Next: python3 {Path(__file__).with_name('tally.py')} {a.out} --sheet")


if __name__ == "__main__":
    main()
