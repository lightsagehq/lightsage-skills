#!/usr/bin/env python3
"""Measure whether each skill fires on the prompts in skills/*/evals/evals.json.

For every prompt in `trigger.should_fire` and `trigger.should_not_fire`, start a
fresh agent session with all skills in this repo installed and record which
skills it loads on its first move. Sessions run in a throwaway project under the
system temp dir, with no user settings, memories, MCP servers or other skills.

  python3 evals/run_triggers.py --harness claude --runs 3
  python3 evals/run_triggers.py --harness codex --skill test-agent-pick --runs 1
  python3 evals/run_triggers.py --report results/triggers-claude.jsonl

Uses your own Claude Code or Codex login. Each prompt x run is one short session.
"""
import argparse, concurrent.futures as cf, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"


def load_cases(only):
    cases = []
    for f in sorted(SKILLS.glob("*/evals/evals.json")):
        name = f.parent.parent.name
        if only and name not in only:
            continue
        data = json.loads(f.read_text())
        trig = data.get("trigger", {})
        for kind in ("should_fire", "should_not_fire"):
            for p in trig.get(kind, []):
                cases.append({"skill": name, "kind": kind, "prompt": p})
    return cases


def make_sandbox(harness):
    base = Path(os.popen("getconf DARWIN_USER_TEMP_DIR").read().strip() or tempfile.gettempdir())
    root = Path(tempfile.mkdtemp(prefix="sk-trig-", dir=base))
    proj = root / "proj"
    proj.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=proj)
    dest = proj / (".claude/skills" if harness == "claude" else ".agents/skills")
    dest.mkdir(parents=True)
    for d in SKILLS.iterdir():
        if (d / "SKILL.md").exists():
            shutil.copytree(d, dest / d.name, ignore=shutil.ignore_patterns("evals"))
    env = dict(os.environ)
    if harness == "codex":
        home = root / "home"; ch = root / "codex-home"
        home.mkdir(); ch.mkdir()
        auth = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "auth.json"
        if not auth.exists():
            sys.exit("No Codex login found (auth.json). Run `codex login` first.")
        (ch / "auth.json").symlink_to(auth)
        (ch / "config.toml").write_text('[features]\napps = false\nplugins = false\nmemories = false\n')
        env.update(HOME=str(home), CODEX_HOME=str(ch))
    else:
        env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
    return root, proj, env


SKILL_PATH = re.compile(r"skills/([a-z0-9-]+)/SKILL\.md")


def run_claude(prompt, proj, env, model, timeout):
    cmd = ["claude", "-p", prompt, "--setting-sources", "project", "--strict-mcp-config",
           "--output-format", "stream-json", "--verbose", "--max-turns", "1"]
    if model:
        cmd += ["--model", model]
    fired = []
    try:
        p = subprocess.run(cmd, cwd=proj, env=env, stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=timeout)
        out = p.stdout
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "assistant":
            for c in ev["message"].get("content", []):
                if c.get("type") == "tool_use":
                    if c["name"] == "Skill":
                        fired.append(str(c["input"].get("skill", "")).split(":")[-1])
                    else:
                        m = SKILL_PATH.search(json.dumps(c.get("input", {})))
                        if m:
                            fired.append(m.group(1))
    return fired


def run_codex(prompt, proj, env, model, timeout):
    cmd = ["codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only", prompt]
    if model:
        cmd[2:2] = ["-m", model]
    fired, cmds = [], 0
    p = subprocess.Popen(cmd, cwd=proj, env=env, stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    start = time.time()
    try:
        for line in p.stdout:
            if time.time() - start > timeout:
                break
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            it = ev.get("item", {})
            if ev.get("type") == "item.started" and it.get("type") == "command_execution":
                cmds += 1
                fired += SKILL_PATH.findall(it.get("command", ""))
                if cmds >= 3:  # the first moves are enough to see which skills it loads
                    break
            if ev.get("type") == "item.completed" and it.get("type") == "agent_message" and cmds and not fired:
                pass
            if ev.get("type") in ("turn.completed", "turn.failed"):
                break
    finally:
        p.kill()
    return fired


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--harness", choices=["claude", "codex"], default="claude")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--skill", action="append", help="only this skill's prompts (repeatable)")
    ap.add_argument("--model")
    ap.add_argument("--parallel", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--out", help="JSONL output path (default results/triggers-<harness>.jsonl)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", help="only print the report for an existing JSONL file")
    a = ap.parse_args()

    if a.report:
        report([json.loads(l) for l in open(a.report)])
        return
    cases = load_cases(a.skill)
    jobs = [dict(c, run=r) for c in cases for r in range(a.runs)]
    print(f"{len(cases)} prompts x {a.runs} runs = {len(jobs)} {a.harness} sessions", file=sys.stderr)
    if a.dry_run or not jobs:
        return
    out = Path(a.out or REPO / "evals" / "results" / f"triggers-{a.harness}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    runner = run_claude if a.harness == "claude" else run_codex
    rows = []

    def one(job):
        root, proj, env = make_sandbox(a.harness)
        try:
            fired = runner(job["prompt"], proj, env, a.model, a.timeout)
        finally:
            shutil.rmtree(root, ignore_errors=True)
        return dict(job, harness=a.harness, model=a.model, fired=sorted(set(fired)))

    with cf.ThreadPoolExecutor(a.parallel) as ex, open(out, "a") as fh:
        for i, row in enumerate(ex.map(one, jobs), 1):
            rows.append(row)
            fh.write(json.dumps(row) + "\n"); fh.flush()
            print(f"[{i}/{len(jobs)}] {row['skill']:24} {row['kind']:15} fired={row['fired']}", file=sys.stderr)
    report(rows)
    print(f"\nwrote {out}", file=sys.stderr)


def report(rows):
    by = {}
    for r in rows:
        s = by.setdefault(r["skill"], {"fire_ok": 0, "fire_n": 0, "false": 0, "neg_n": 0, "misroute": {}})
        hit = r["skill"] in r["fired"]
        if r["kind"] == "should_fire":
            s["fire_n"] += 1; s["fire_ok"] += hit
            for o in r["fired"]:
                if o != r["skill"]:
                    s["misroute"][o] = s["misroute"].get(o, 0) + 1
        else:
            s["neg_n"] += 1; s["false"] += hit
    print("| Skill | Fires when it should | Fires when it shouldn't | Other skills loaded instead/also |")
    print("|---|---|---|---|")
    for k, s in sorted(by.items()):
        rec = f"{s['fire_ok']}/{s['fire_n']} ({100*s['fire_ok']//max(s['fire_n'],1)}%)"
        fp = f"{s['false']}/{s['neg_n']} ({100*s['false']//max(s['neg_n'],1)}%)"
        mis = ", ".join(f"{o} x{n}" for o, n in sorted(s["misroute"].items(), key=lambda x: -x[1])) or "-"
        print(f"| {k} | {rec} | {fp} | {mis} |")


if __name__ == "__main__":
    main()
