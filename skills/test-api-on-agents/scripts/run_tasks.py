#!/usr/bin/env python3
"""Run every task in a suite N times on local coding-agent CLIs, each attempt in a
fresh, isolated directory, and save transcripts, timings and check results.

Without --yes it only prints the plan (session count, credentials by name,
isolation) and exits; nothing is started. Show that plan to the user and get a
yes before re-running with --yes.

Examples:
  python3 run_tasks.py tasks.json --dry-run
  python3 run_tasks.py tasks.json --agents claude,codex --runs 3 --yes
  python3 run_tasks.py tasks.json --only send-email --agents codex --runs 5 --yes

Output (default ./agent-test-runs/<suite>-<timestamp>/):
  plan.json
  <task>/<agent>/run-<k>/{prompt.txt,transcript.jsonl,stderr.txt,final.txt,
                          events.jsonl,meta.json,check.json,setup.txt}
Then: python3 tally.py <out-dir>
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402
import check as CHECK  # noqa: E402

AGENTS = ("claude", "codex")
PRINT_LOCK = threading.Lock()


def log(msg: str) -> None:
    with PRINT_LOCK:
        print(msg, flush=True)


def which_version(binary: str) -> Optional[str]:
    path = shutil.which(binary)
    if not path:
        return None
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=30,
                             stdin=subprocess.DEVNULL)
        return (out.stdout or out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"


def ancestors_with_context(path: Path) -> List[str]:
    hits = []
    for d in [path] + list(path.parents):
        for name in (".git", "AGENTS.md", "CLAUDE.md", ".claude", ".mcp.json"):
            if (d / name).exists():
                hits.append(str(d / name))
    return hits


# ---------------------------------------------------------------- agent commands

def claude_mcp_json(suite: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    servers = suite.get("mcp_servers") or {}
    if not servers:
        return None
    out = {}
    for name, s in servers.items():
        if s.get("url"):
            entry: Dict[str, Any] = {"type": "http", "url": s["url"]}
            if s.get("bearer_env"):
                entry["headers"] = {"Authorization": "Bearer ${%s}" % s["bearer_env"]}
        else:
            entry = {"command": s["command"], "args": s.get("args", [])}
            if s.get("env"):
                entry["env"] = {n: "${%s}" % n for n in s["env"]}
        out[name] = entry
    return {"mcpServers": out}


def toml_str(v: str) -> str:
    return json.dumps(v)  # JSON string escaping is valid TOML basic-string escaping


def codex_config(suite: Dict[str, Any], effort: Optional[str]) -> str:
    lines = ['web_search = "live"']
    if effort:
        lines.append(f"model_reasoning_effort = {toml_str(effort)}")
    lines += ["", "[sandbox_workspace_write]", "network_access = true", "",
              "[features]", "apps = false", "plugins = false", "memories = false", "hooks = false"]
    for name, s in (suite.get("mcp_servers") or {}).items():
        lines += ["", f"[mcp_servers.{name}]"]
        if s.get("url"):
            lines.append(f"url = {toml_str(s['url'])}")
            if s.get("bearer_env"):
                lines.append(f"bearer_token_env_var = {toml_str(s['bearer_env'])}")
        else:
            lines.append(f"command = {toml_str(s['command'])}")
            lines.append("args = [" + ", ".join(toml_str(a) for a in s.get("args", [])) + "]")
            if s.get("env"):
                lines.append("env_vars = [" + ", ".join(toml_str(n) for n in s["env"]) + "]")
    return "\n".join(lines) + "\n"


def build_claude(args, prompt: str, root: Path, suite: Dict[str, Any], names: List[str]):
    isolated = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
    if isolated:
        home = root / "home"
        home.mkdir(parents=True, exist_ok=True)
        extra = {"CLAUDE_CODE_OAUTH_TOKEN": os.environ["CLAUDE_CODE_OAUTH_TOKEN"]}
    else:
        home = Path.home()
        extra = {}
    extra["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
    cmd = [args.claude_bin, "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--setting-sources", "", "--settings", '{"autoMemoryEnabled":false}',
           "--strict-mcp-config", "--disable-slash-commands", "--no-session-persistence",
           "--dangerously-skip-permissions"]
    mcp = claude_mcp_json(suite)
    if mcp:
        p = root / "mcp.json"
        p.write_text(json.dumps(mcp, indent=2))
        cmd += ["--mcp-config", str(p)]
    if args.claude_model:
        cmd += ["--model", args.claude_model]
    env = C.child_env(names, str(home), extra)
    return cmd, env, ("home+config" if isolated else "config-only (real HOME)")


def build_codex(args, prompt: str, root: Path, suite: Dict[str, Any], names: List[str], workdir: Path):
    home = root / "home"
    codex_home = home / ".codex"
    codex_home.mkdir(parents=True, exist_ok=True)
    auth = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))) / "auth.json"
    if auth.exists():
        link = codex_home / "auth.json"
        if not link.exists():
            link.symlink_to(auth)
    (codex_home / "config.toml").write_text(codex_config(suite, args.codex_effort))
    extra = {"CODEX_HOME": str(codex_home)}
    for k in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        if not auth.exists() and os.environ.get(k):
            extra[k] = os.environ[k]
    cmd = [args.codex_bin, "exec", "--json", "--skip-git-repo-check", "--ephemeral",
           "-C", str(workdir), "-s", "workspace-write", "-o", str(root / "final.raw.txt")]
    if args.codex_model:
        cmd += ["-m", args.codex_model]
    cmd.append(prompt)
    env = C.child_env(names, str(home), extra)
    return cmd, env, "home+config"


# ---------------------------------------------------------------- one attempt

def kill_tree(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=10)
    except (ProcessLookupError, subprocess.TimeoutExpired, PermissionError):
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def run_attempt(args, suite, task, agent: str, k: int, out_dir: Path, tmp_root: Path) -> Dict[str, Any]:
    adir = out_dir / task["id"] / agent / f"run-{k}"
    adir.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=f"{task['id']}-{agent}-{k}-", dir=str(tmp_root)))
    workdir = root / "work"
    workdir.mkdir()
    names = C.task_env_names(suite, task)
    secrets = C.secret_values(names)
    timeout = int(task.get("timeout_sec") or suite.get("timeout_sec") or 600)
    meta: Dict[str, Any] = {"task": task["id"], "agent": agent, "run": k, "workdir": str(workdir),
                            "started_at": datetime.now(timezone.utc).isoformat(), "timeout_sec": timeout,
                            "env_names": names, "env_missing": [n for n in names if n not in os.environ]}
    (adir / "prompt.txt").write_text(task["prompt"])

    if agent == "claude":
        cmd, env, iso = build_claude(args, task["prompt"], root, suite, names)
    else:
        cmd, env, iso = build_codex(args, task["prompt"], root, suite, names, workdir)
    meta["isolation"] = iso
    meta["model"] = args.claude_model if agent == "claude" else args.codex_model

    setup_cmds = list(suite.get("setup") or []) + list(task.get("setup") or [])
    if setup_cmds:
        setup_env = C.child_env(names, env["HOME"])
        with open(adir / "setup.txt", "w") as fh:
            for sc in setup_cmds:
                fh.write(f"$ {sc}\n")
                fh.flush()
                r = subprocess.run(sc, shell=True, cwd=str(workdir), env=setup_env, stdout=fh,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=600)
                if r.returncode != 0:
                    meta["harness_error"] = f"setup command failed ({r.returncode}): {sc}"
                    break
        C.redact_file(adir / "setup.txt", secrets)
        if meta.get("harness_error"):
            meta["status"] = "harness_error"
            (adir / "meta.json").write_text(json.dumps(meta, indent=2))
            log(f"  {task['id']} / {agent} / run-{k}: setup failed, see {adir / 'setup.txt'}")
            return meta

    t0 = time.monotonic()
    timed_out = False
    with open(adir / "transcript.jsonl", "w") as out, open(adir / "stderr.txt", "w") as err:
        proc = subprocess.Popen(cmd, cwd=str(workdir), env=env, stdout=out, stderr=err,
                                stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(proc)
    meta["duration_sec"] = round(time.monotonic() - t0, 1)
    meta["exit_code"] = proc.returncode
    meta["timed_out"] = timed_out

    raw_final = root / "final.raw.txt"
    if raw_final.exists():
        shutil.copyfile(raw_final, adir / "final.txt")
    for f in ("transcript.jsonl", "stderr.txt", "final.txt"):
        C.redact_file(adir / f, secrets)

    parsed = C.parse_transcript(agent, adir / "transcript.jsonl")
    if not (adir / "final.txt").exists():
        (adir / "final.txt").write_text(parsed.get("final_text") or "")
        C.redact_file(adir / "final.txt", secrets)
    with open(adir / "events.jsonl", "w") as fh:
        for ev in parsed["events"]:
            fh.write(C.redact(json.dumps(ev, ensure_ascii=False), secrets) + "\n")
    for key in ("turns", "cost_usd", "tool_calls", "signals", "urls", "failing_urls", "tokens"):
        if parsed.get(key) is not None:
            meta[key] = parsed[key]
    if timed_out:
        meta["status"] = "timeout"
    elif parsed.get("harness_error"):
        meta["status"] = "harness_error"
        meta["harness_error"] = C.redact(parsed["harness_error"], secrets)
    else:
        meta["status"] = "finished"
    (adir / "meta.json").write_text(json.dumps(meta, indent=2))

    if not args.no_check and meta["status"] != "harness_error":
        res = CHECK.run_check(suite, task, adir, meta)
        meta["check_passed"] = res["passed"]
    verdict = {True: "PASS", False: "FAIL", None: "-"}[meta.get("check_passed")]
    log(f"  {task['id']} / {agent} / run-{k}: {meta['status']} {verdict} "
        f"{meta['duration_sec']}s, {meta.get('tool_calls', 0)} tool calls")
    return meta


# ---------------------------------------------------------------- plan + main

def print_plan(args, suite, tasks, agents, out_dir: Path, versions: Dict[str, Optional[str]], tmp_root: Path) -> int:
    sessions = len(tasks) * len(agents) * args.runs
    timeout = max(int(t.get("timeout_sec") or suite.get("timeout_sec") or 600) for t in tasks)
    waves = -(-sessions // max(1, args.parallel))
    print(f"Suite: {suite['suite']}  ({suite['_path']})")
    print(f"Tasks: {len(tasks)}  Agents: {', '.join(agents)}  Runs per task per agent: {args.runs}")
    print(f"=> {sessions} agent sessions on your own subscriptions/API keys "
          f"({args.parallel} at a time; worst case ~{waves * timeout // 60} min at the {timeout}s timeout, "
          f"usually far less)")
    for a in agents:
        print(f"   {a}: {versions.get(a) or 'NOT FOUND on PATH'}")
    names: List[str] = []
    for t in tasks:
        for n in C.task_env_names(suite, t):
            if n not in names:
                names.append(n)
    if names:
        print("Credentials passed by env var (names only): " +
              ", ".join(f"{n} [{'set' if n in os.environ else 'MISSING'}]" for n in names))
        print("  WARNING: agents can read these values and use them for real API calls.")
        print("  Use a test/sandbox key with the narrowest scope; values are redacted from saved files.")
    else:
        print("Credentials: none (agents get no product keys)")
    if suite.get("mcp_servers"):
        print("MCP servers attached: " + ", ".join(suite["mcp_servers"]))
    print("Isolation: fresh temp dir per attempt under " + str(tmp_root))
    print("  claude: --setting-sources '' --strict-mcp-config --disable-slash-commands, no CLAUDE.md, no auto-memory;"
          + (" isolated HOME (CLAUDE_CODE_OAUTH_TOKEN set)" if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
             else " real HOME (set CLAUDE_CODE_OAUTH_TOKEN from `claude setup-token` to isolate it)"))
    print("  codex: temp HOME + CODEX_HOME (auth linked), no apps/plugins/memories/hooks/AGENTS.md,"
          " workspace-write sandbox with network")
    print("  Agents run shell commands without asking (claude: --dangerously-skip-permissions). "
          "Use a VM or container for anything you would not run yourself.")
    ctx = ancestors_with_context(tmp_root)
    if ctx:
        print("  WARNING: temp root sits under agent context files that may leak in: " + ", ".join(ctx))
    if args.claude_model or args.codex_model:
        print(f"Models: claude={args.claude_model or 'default'} codex={args.codex_model or 'default'}")
    print(f"Output: {out_dir}")
    missing = [a for a in agents if not versions.get(a)]
    if missing:
        print(f"ERROR: not installed: {', '.join(missing)}")
        return 1
    if any(n not in os.environ for n in names):
        print("ERROR: a credential named in the suite is not set in this shell; export it first.")
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks", help="suite JSON file (see references/tasks-and-checks.md)")
    ap.add_argument("--agents", default="claude,codex", help="comma list from: claude,codex (default both)")
    ap.add_argument("--runs", type=int, default=3, help="attempts per task per agent (default 3; use 5+ for decisions)")
    ap.add_argument("--only", default="", help="comma list of task ids to run")
    ap.add_argument("--parallel", type=int, default=2, help="sessions at a time (default 2)")
    ap.add_argument("--out", default="", help="output dir (default ./agent-test-runs/<suite>-<timestamp>)")
    ap.add_argument("--claude-bin", default="claude")
    ap.add_argument("--codex-bin", default="codex")
    ap.add_argument("--claude-model", default="", help="e.g. sonnet, opus, haiku (default: CLI default)")
    ap.add_argument("--codex-model", default="", help="e.g. a GPT model id (default: CLI default)")
    ap.add_argument("--codex-effort", default="", help="model_reasoning_effort for codex (low|medium|high)")
    ap.add_argument("--no-check", action="store_true", help="skip running success checks after each attempt")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    ap.add_argument("--yes", action="store_true", help="start the sessions (only after the user agreed to the plan)")
    args = ap.parse_args(argv)

    try:
        suite = C.load_suite(args.tasks)
    except C.SuiteError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    bad = [a for a in agents if a not in AGENTS]
    if bad:
        print(f"ERROR: unknown agent(s) {bad}; supported: {', '.join(AGENTS)}", file=sys.stderr)
        return 2
    if args.runs < 1:
        print("ERROR: --runs must be >= 1", file=sys.stderr)
        return 2
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    tasks = [t for t in suite["tasks"] if not only or t["id"] in only]
    if not tasks:
        print(f"ERROR: no tasks match --only {sorted(only)}", file=sys.stderr)
        return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out or f"agent-test-runs/{suite['suite']}-{stamp}").resolve()
    tmp_root = Path(tempfile.gettempdir()).resolve() / "agent-test-work"
    versions = {a: which_version(args.claude_bin if a == "claude" else args.codex_bin) for a in agents}

    rc = print_plan(args, suite, tasks, agents, out_dir, versions, tmp_root)
    if args.runs < 3:
        print(f"NOTE: --runs {args.runs} is below 3; treat results as a smoke test, not a pass rate.")
    if rc:
        return rc
    if args.dry_run or not args.yes:
        print("\nNOT STARTED." + ("" if args.dry_run else
              " Show this plan to the user; after they agree, re-run with --yes."))
        return 0 if args.dry_run else 3

    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_root.mkdir(parents=True, exist_ok=True)
    plan = {"suite": suite["suite"], "tasks_file": suite["_path"], "agents": agents, "runs": args.runs,
            "task_ids": [t["id"] for t in tasks], "versions": versions,
            "models": {"claude": args.claude_model or None, "codex": args.codex_model or None},
            "created_at": datetime.now(timezone.utc).isoformat()}
    (out_dir / "plan.json").write_text(json.dumps(plan, indent=2))
    jobs = [(t, a, k) for k in range(1, args.runs + 1) for t in tasks for a in agents]
    log(f"\nStarting {len(jobs)} sessions...")
    with cf.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
        futs = [ex.submit(run_attempt, args, suite, t, a, k, out_dir, tmp_root) for t, a, k in jobs]
        for f in cf.as_completed(futs):
            exc = f.exception()
            if exc:
                log(f"  attempt crashed in the runner: {exc!r}")
    log(f"\nDone. Next: python3 {Path(__file__).with_name('tally.py')} {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
