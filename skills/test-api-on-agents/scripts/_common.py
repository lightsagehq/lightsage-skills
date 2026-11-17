"""Shared helpers for run_tasks.py, check.py and tally.py (stdlib only).

Not a CLI. Holds the suite loader, secret redaction, and the parsers that turn
Claude Code stream-json and Codex --json transcripts into one event shape.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

# ---------------------------------------------------------------- suite file

SUITE_KEYS = {"suite", "env", "setup", "mcp_servers", "timeout_sec", "tasks"}
TASK_KEYS = {"id", "prompt", "check", "timeout_sec", "setup", "env"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class SuiteError(ValueError):
    pass


def load_suite(path: str) -> Dict[str, Any]:
    p = Path(path).expanduser().resolve()
    try:
        data = json.loads(p.read_text())
    except FileNotFoundError:
        raise SuiteError(f"tasks file not found: {p}")
    except json.JSONDecodeError as e:
        raise SuiteError(f"tasks file is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise SuiteError("tasks file must be a JSON object")
    unknown = set(data) - SUITE_KEYS
    if unknown:
        raise SuiteError(f"unknown top-level keys: {sorted(unknown)} (allowed: {sorted(SUITE_KEYS)})")
    tasks = data.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise SuiteError("'tasks' must be a non-empty list")
    seen = set()
    for t in tasks:
        if not isinstance(t, dict):
            raise SuiteError("each task must be an object")
        bad = set(t) - TASK_KEYS
        if bad:
            raise SuiteError(f"task {t.get('id')!r}: unknown keys {sorted(bad)}")
        tid = t.get("id")
        if not isinstance(tid, str) or not ID_RE.match(tid):
            raise SuiteError(f"task id {tid!r} must be lowercase letters, digits, - or _")
        if tid in seen:
            raise SuiteError(f"duplicate task id {tid!r}")
        seen.add(tid)
        if not isinstance(t.get("prompt"), str) or not t["prompt"].strip():
            raise SuiteError(f"task {tid!r}: 'prompt' is required")
        if not isinstance(t.get("check"), str) or not t["check"].strip():
            raise SuiteError(f"task {tid!r}: 'check' is required (a shell command that exits 0 on success)")
    data.setdefault("suite", p.stem)
    data.setdefault("env", [])
    data.setdefault("setup", [])
    data.setdefault("mcp_servers", {})
    data.setdefault("timeout_sec", 600)
    data["_path"] = str(p)
    data["_dir"] = str(p.parent)
    return data


def task_env_names(suite: Dict[str, Any], task: Dict[str, Any]) -> List[str]:
    names = list(suite.get("env") or []) + list(task.get("env") or [])
    for srv in (suite.get("mcp_servers") or {}).values():
        if srv.get("bearer_env"):
            names.append(srv["bearer_env"])
        names.extend(srv.get("env") or [])
    out: List[str] = []
    for n in names:
        if n not in out:
            out.append(n)
    return out


# ---------------------------------------------------------------- env + redaction

BASE_ENV = ["PATH", "USER", "LOGNAME", "SHELL", "TERM", "LANG", "LC_ALL", "LC_CTYPE",
            "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS",
            "__CF_USER_TEXT_ENCODING"]


def child_env(names: Iterable[str], home: str, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Allowlisted env: base vars + the named credentials. Nothing else leaks in."""
    env = {k: os.environ[k] for k in BASE_ENV if k in os.environ}
    env["HOME"] = home
    for n in names:
        if n in os.environ:
            env[n] = os.environ[n]
    if extra:
        env.update(extra)
    return env


def secret_values(names: Iterable[str]) -> Dict[str, str]:
    out = {}
    for n in names:
        v = os.environ.get(n)
        if v and len(v) >= 6:
            out[n] = v
    return out


def redact(text: str, secrets: Dict[str, str]) -> str:
    # longest first so a value that contains another is replaced whole
    for name, val in sorted(secrets.items(), key=lambda kv: -len(kv[1])):
        text = text.replace(val, f"[REDACTED:{name}]")
    return text


def redact_file(path: Path, secrets: Dict[str, str]) -> None:
    if not secrets or not path.exists():
        return
    raw = path.read_text(errors="replace")
    clean = redact(raw, secrets)
    if clean != raw:
        path.write_text(clean)


# ---------------------------------------------------------------- transcripts

URL_RE = re.compile(r"https?://[^\s'\"<>)\]}`\\]+")

SIGNALS = [
    ("auth", re.compile(r"\b(401|403)\b|unauthori[sz]ed|forbidden|invalid[ _-]?api[ _-]?key|"
                        r"authentication (failed|required)|missing (api )?key|permission denied for", re.I)),
    ("not_found_404", re.compile(r"\b404\b|not found\b", re.I)),
    ("package_missing", re.compile(r"ModuleNotFoundError|No module named|Cannot find module|"
                                   r"No matching distribution|E404|is not in (the|this) registry|"
                                   r"Could not resolve dependency|command not found", re.I)),
    ("hallucinated_api", re.compile(r"AttributeError|has no attribute|is not a function|undefined method|"
                                    r"unexpected keyword argument|got an unexpected|Unknown (argument|option|flag|command)|"
                                    r"unrecognized arguments|no such (command|option)|does not exist on type|"
                                    r"Property '[^']+' does not exist|has no exported member|cannot import name", re.I)),
    ("deprecated", re.compile(r"deprecat", re.I)),
    ("rate_limited", re.compile(r"\b429\b|rate[ -]?limit|too many requests", re.I)),
    ("server_error", re.compile(r"\b50[0234]\b|internal server error|bad gateway|service unavailable", re.I)),
    ("validation", re.compile(r"\b(400|422)\b|validation error|invalid (request|parameter|value)|is required\b", re.I)),
    ("network", re.compile(r"ECONNREFUSED|ENOTFOUND|getaddrinfo|Name or service not known|"
                           r"Connection refused|timed out|SSL: CERTIFICATE", re.I)),
]


def _short(v: Any, n: int = 400) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        try:
            v = json.dumps(v, ensure_ascii=False)
        except (TypeError, ValueError):
            v = str(v)
    v = v.replace("\r", "")
    return v if len(v) <= n else v[: n - 3] + "..."


def _content_text(c: Any) -> str:
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for item in c:
            if isinstance(item, dict):
                parts.append(item.get("text") or item.get("content") or "")
            else:
                parts.append(str(item))
        return "\n".join(p if isinstance(p, str) else json.dumps(p) for p in parts)
    if isinstance(c, dict):
        return c.get("text") or json.dumps(c)
    return str(c or "")


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def parse_claude(path: Path) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    pending: Dict[str, Dict[str, Any]] = {}
    result: Dict[str, Any] = {}
    final_text = ""
    for e in _read_jsonl(path):
        t = e.get("type")
        if t == "assistant":
            for c in (e.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use":
                    ev = {"kind": "tool", "name": c.get("name"), "input": _short(c.get("input"), 600),
                          "output": "", "error": False}
                    inp = c.get("input") or {}
                    if isinstance(inp, dict) and inp.get("url"):
                        ev["url"] = inp["url"]
                    pending[c.get("id")] = ev
                    events.append(ev)
                elif c.get("type") == "text" and c.get("text"):
                    final_text = c["text"]
        elif t == "user":
            for c in (e.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    ev = pending.get(c.get("tool_use_id"))
                    if ev is not None:
                        ev["output"] = _short(_content_text(c.get("content")), 1500)
                        ev["error"] = bool(c.get("is_error"))
        elif t == "result":
            result = e
    harness_error = None
    if not result:
        harness_error = "no result event (agent crashed, was killed, or timed out)"
    elif result.get("is_error") and re.search(r"not logged in|/login|invalid api key|credit balance", str(result.get("result")), re.I):
        harness_error = _short(result.get("result"), 200)
    return {
        "events": events,
        "turns": result.get("num_turns"),
        "cost_usd": result.get("total_cost_usd"),
        "final_text": result.get("result") if isinstance(result.get("result"), str) else final_text,
        "harness_error": harness_error,
    }


def parse_codex(path: Path) -> Dict[str, Any]:
    events: List[Dict[str, Any]] = []
    turns = 0
    final_text = ""
    errors: List[str] = []
    usage_in = usage_out = 0
    for e in _read_jsonl(path):
        t = e.get("type")
        if t == "turn.completed":
            turns += 1
            u = e.get("usage") or {}
            usage_in += int(u.get("input_tokens") or 0)
            usage_out += int(u.get("output_tokens") or 0)
        elif t in ("error", "turn.failed"):
            errors.append(_short(e.get("message") or e.get("error"), 300))
        elif t == "item.completed":
            it = e.get("item") or {}
            ty = it.get("type")
            if ty == "agent_message":
                final_text = it.get("text") or final_text
            elif ty == "command_execution":
                out = it.get("aggregated_output") or ""
                events.append({"kind": "tool", "name": "shell", "input": _short(it.get("command"), 600),
                               "output": _short(out, 1500),
                               "error": (it.get("exit_code") not in (0, None)) or it.get("status") == "failed"})
            elif ty == "mcp_tool_call":
                events.append({"kind": "tool", "name": f"mcp:{it.get('server')}.{it.get('tool')}",
                               "input": _short(it.get("arguments"), 600),
                               "output": _short(it.get("result") or it.get("error"), 1500),
                               "error": bool(it.get("error")) or it.get("status") == "failed"})
            elif ty == "web_search":
                events.append({"kind": "tool", "name": "web_search", "input": _short(it.get("query"), 300),
                               "output": "", "error": False})
            elif ty == "file_change":
                events.append({"kind": "tool", "name": "file_change", "input": _short(it.get("changes"), 300),
                               "output": "", "error": it.get("status") == "failed"})
    harness_error = None
    if turns == 0 and not events:
        harness_error = errors[0] if errors else "no turn completed (agent crashed, was killed, or timed out)"
    elif errors and re.search(r"auth|login|401|unauthori", " ".join(errors), re.I) and not events:
        harness_error = errors[0]
    # codex exec runs one user turn; it has no per-step turn count, so compare tool calls instead
    return {"events": events, "turns": None, "cost_usd": None, "final_text": final_text,
            "harness_error": harness_error, "tokens": {"input": usage_in, "output": usage_out}}


def summarize_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    signals: Dict[str, int] = {}
    urls: List[str] = []
    failing_urls: List[str] = []
    for ev in events:
        text_in = ev.get("input") or ""
        text_out = ev.get("output") or ""
        found = [ev["url"]] if ev.get("url") else []
        found += URL_RE.findall(text_in)
        for u in found:
            u = u.rstrip(".,;:")
            if u not in urls:
                urls.append(u)
        if ev.get("error") or text_out:
            hit_any = False
            for name, rx in SIGNALS:
                if rx.search(text_out):
                    signals[name] = signals.get(name, 0) + 1
                    hit_any = True
            if found and (ev.get("error") or re.search(r"\b(404|410|403|401)\b", text_out)):
                for u in found:
                    if u not in failing_urls:
                        failing_urls.append(u)
            if ev.get("error") and not hit_any:
                signals["other_tool_error"] = signals.get("other_tool_error", 0) + 1
    return {"tool_calls": len(events), "signals": signals, "urls": urls[:80], "failing_urls": failing_urls[:40]}


def parse_transcript(agent: str, path: Path) -> Dict[str, Any]:
    parsed = parse_claude(path) if agent == "claude" else parse_codex(path)
    parsed.update(summarize_events(parsed["events"]))
    return parsed
