#!/usr/bin/env python3
"""Run (or re-run) each task's success check against finished attempts.

A check is the task's "check" shell command from the suite file. It runs in the
attempt's work directory after the agent has exited, with these variables set:
  WORKDIR             the agent's work directory (also the cwd)
  FINAL_MESSAGE_FILE  the agent's last message, as text
  ATTEMPT_DIR         the saved attempt folder (transcript, events, meta)
  CHECKS_DIR          the folder holding the suite file, for check scripts
plus the credential env vars named in the suite. Exit 0 = pass, anything else = fail.
The agent's own claim of success is never used.

run_tasks.py calls this after every attempt. Run it yourself after fixing a
check, so you do not have to re-run the agents:
  python3 check.py agent-test-runs/acme-20261117-101500
  python3 check.py <out-dir> --task send-email --force
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _common as C  # noqa: E402

CHECK_TIMEOUT = 300


def run_check(suite: Dict[str, Any], task: Dict[str, Any], adir: Path, meta: Dict[str, Any]) -> Dict[str, Any]:
    workdir = Path(meta["workdir"])
    names = C.task_env_names(suite, task)
    secrets = C.secret_values(names)
    if not workdir.exists():
        res = {"passed": None, "error": f"work directory is gone: {workdir}"}
        (adir / "check.json").write_text(json.dumps(res, indent=2))
        return res
    env = C.child_env(names, os.environ.get("HOME", str(Path.home())), {
        "WORKDIR": str(workdir),
        "FINAL_MESSAGE_FILE": str(adir / "final.txt"),
        "ATTEMPT_DIR": str(adir),
        "CHECKS_DIR": suite["_dir"],
    })
    try:
        r = subprocess.run(task["check"], shell=True, cwd=str(workdir), env=env, capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=CHECK_TIMEOUT)
        out = C.redact((r.stdout or "") + (r.stderr or ""), secrets)
        res = {"passed": r.returncode == 0, "exit_code": r.returncode, "output_tail": out[-2000:]}
    except subprocess.TimeoutExpired:
        res = {"passed": False, "exit_code": None, "output_tail": f"check timed out after {CHECK_TIMEOUT}s"}
    res["check"] = task["check"]
    (adir / "check.json").write_text(json.dumps(res, indent=2))
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", help="output folder written by run_tasks.py")
    ap.add_argument("--tasks", default="", help="suite file (default: the one recorded in plan.json)")
    ap.add_argument("--task", default="", help="only this task id")
    ap.add_argument("--force", action="store_true", help="re-run checks that already have a result")
    args = ap.parse_args(argv)

    out = Path(args.out_dir).resolve()
    plan_path = out / "plan.json"
    if not plan_path.exists() and not args.tasks:
        print(f"ERROR: {plan_path} not found; pass --tasks", file=sys.stderr)
        return 2
    suite_file = args.tasks or json.loads(plan_path.read_text())["tasks_file"]
    try:
        suite = C.load_suite(suite_file)
    except C.SuiteError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    by_id = {t["id"]: t for t in suite["tasks"]}
    ran = passed = skipped = 0
    for meta_path in sorted(out.glob("*/*/run-*/meta.json")):
        meta = json.loads(meta_path.read_text())
        if args.task and meta["task"] != args.task:
            continue
        task = by_id.get(meta["task"])
        if task is None:
            print(f"  skip {meta_path.parent}: task {meta['task']!r} no longer in the suite")
            continue
        if meta.get("status") == "harness_error":
            skipped += 1
            continue
        if (meta_path.parent / "check.json").exists() and not args.force:
            res = json.loads((meta_path.parent / "check.json").read_text())
        else:
            res = run_check(suite, task, meta_path.parent, meta)
        ran += 1
        passed += 1 if res.get("passed") else 0
        flag = {True: "PASS", False: "FAIL", None: "NO-WORKDIR"}[res.get("passed")]
        print(f"  {meta['task']} / {meta['agent']} / run-{meta['run']}: {flag}")
    print(f"\n{passed}/{ran} attempts passed their check; {skipped} harness errors not checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
