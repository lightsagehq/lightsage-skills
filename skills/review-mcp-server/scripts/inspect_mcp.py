#!/usr/bin/env python3
"""Inspect a remote MCP server's tool surface without calling any tool.

Connects to a Streamable HTTP MCP endpoint, runs `initialize` and `tools/list`
(following pagination), and prints one row per tool with its title, annotation
hints, description length, approximate schema tokens and review flags. It never
sends `tools/call`.

If the server answers 401, it reads the OAuth discovery metadata instead
(RFC 9728 protected resource metadata and the authorization server's metadata)
and reports what directory reviewers check: S256 PKCE, client registration
(DCR or CIMD) and refresh-token scope.

Python 3.8+ standard library only.

Examples:
  python3 inspect_mcp.py https://example.com/mcp
  MY_TOKEN=... python3 inspect_mcp.py https://example.com/mcp --token-env MY_TOKEN
  python3 inspect_mcp.py https://example.com/mcp --format json > tools.json
  python3 inspect_mcp.py https://example.com/mcp --save-raw tools-list.json

Exit codes: 0 tools listed, 2 auth required (401/403), 1 other failure.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

PROTOCOL_VERSION = "2025-11-25"
CLIENT_INFO = {"name": "mcp-surface-inspector", "version": "1.0.0"}
TOOL_COUNT_LIMIT = 40
TOTAL_TOKEN_LIMIT = 10_000
SCHEMA_TOKEN_LIMIT = 1_000

FLAG_HELP = {
    "no-title": "no human-readable title (tool.title or annotations.title); Claude's directory requires one",
    "no-readonly-hint": "readOnlyHint not declared; clients assume a write that may be destructive",
    "no-destructive-hint": "write tool without an explicit destructiveHint",
    "no-openworld-hint": "openWorldHint not declared; OpenAI wants all three hints explicit",
    "hint-conflict": "readOnlyHint and destructiveHint are both true",
    "read-name-not-readonly": "name reads like a lookup but readOnlyHint is not true (check the real behavior)",
    "write-name-marked-readonly": "name reads like a write but readOnlyHint is true",
    "delete-name-not-destructive": "name reads like delete/cancel/overwrite but destructiveHint is not true",
    "mentions-tool": "description names another tool on this server; Google's policy bars referencing other tools, Claude bars steering them",
    "steers-calls": "description tells the model to always/never/first call or use something",
    "external-instructions": "description points the model at instructions from an outside source",
    "rest-path": "description leaks REST paths (GET /v1/...); describe the job, not the route",
    "dispatcher": "generic executor/dispatcher shape (method/operation/endpoint argument or run/execute/call name)",
    "mega-schema": "large or deeply nested input schema (oneOf/anyOf, depth > 3, or > 1,000 tokens)",
    "desc-thin": "description under 40 characters",
    "desc-missing": "no description",
    "name-too-long": "tool name over 64 characters (Claude's directory limit)",
}

READ_VERBS = r"^(get|list|search|find|fetch|read|retrieve|lookup|look_up|query|describe|show|count|check|preview|status)([_\-.]|$)"
WRITE_VERBS = r"(^|[_\-.])(create|add|update|set|put|post|send|delete|remove|cancel|archive|run|start|trigger|write|upload|publish|move|merge|approve|enqueue)([_\-.]|$)"
DELETE_VERBS = r"(^|[_\-.])(delete|remove|destroy|purge|cancel|revoke|overwrite|archive|drop|reset)([_\-.]|$)"
DISPATCH_NAMES = (r"^(execute|exec|dispatch|invoke|proxy|call|run|perform|do)([_\-.]?(api|request|operation|action|tool|command|endpoint|query))?$"
                  r"|(^|[_\-.])(api[_\-.]?request|raw[_\-.]?request|http[_\-.]?request|graphql|rpc|call[_\-.]?tool|use[_\-.]?tool"
                  r"|run[_\-.]?operation|execute[_\-.]?\w+|dispatch[_\-.]?\w+|manage[_\-.]\w+)([_\-.]|$)")
DISPATCH_ARGS = {"method", "http_method", "operation", "operation_id", "operationid", "action",
                 "endpoint", "path", "route", "tool", "tool_name", "toolname", "command", "query_path"}
STEER_RE = re.compile(
    r"\b(always|never|must|first|before any|do not|don't)\s+(call|use|invoke|run|choose|pick|prefer)\b"
    r"|\bprefer (this|these) tools?\b|\binstead of (any|other)\b|\bignore (previous|prior|other|all)\b",
    re.I)
EXTERNAL_RE = re.compile(
    r"(fetch|read|load|follow|download|get)\s+(the\s+)?(latest\s+)?(instructions|rules|guidelines|prompt|system prompt)\s+(from|at)\b"
    r"|instructions\s+(are\s+)?(at|in)\s+https?://",
    re.I)
REST_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+/[\w{}/\-.]+|`/v\d+/[\w{}/\-.]+`|\s/v\d+/[\w{}\-.]+/")


SELF_REF_RE = re.compile(r"\s+(it|this|these|that)\b", re.I)


def steers(text):
    """True when text tells the model to always/never call something other than this tool."""
    for match in STEER_RE.finditer(text or ""):
        negative = (match.group(1) or "").lower() in ("never", "do not", "don't")
        if negative and SELF_REF_RE.match(text, match.end()):
            continue  # "do not call it unprompted" limits the tool itself, which is fine
        return True
    return False


def est_tokens(obj):
    text = obj if isinstance(obj, str) else json.dumps(obj, separators=(",", ":"))
    return (len(text) + 3) // 4


def schema_depth(node, depth=0):
    if isinstance(node, dict):
        props = node.get("properties")
        child = [schema_depth(v, depth + 1) for v in props.values()] if isinstance(props, dict) else []
        for key in ("items", "additionalProperties"):
            if isinstance(node.get(key), dict):
                child.append(schema_depth(node[key], depth + 1))
        for key in ("oneOf", "anyOf", "allOf"):
            if isinstance(node.get(key), list):
                child.extend(schema_depth(v, depth) for v in node[key])
        return max(child) if child else depth
    return depth


def has_union(node):
    if isinstance(node, dict):
        if any(isinstance(node.get(k), list) for k in ("oneOf", "anyOf")):
            return True
        return any(has_union(v) for v in node.values())
    if isinstance(node, list):
        return any(has_union(v) for v in node)
    return False


class HttpStatusError(Exception):
    def __init__(self, status, headers, body):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.headers = headers
        self.body = body


class McpClient:
    def __init__(self, url, headers, timeout):
        self.url = url
        self.headers = headers
        self.timeout = timeout
        self.session_id = None
        self.protocol_version = None
        self._id = 0

    def _post(self, payload, expect_response=True):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": f"{CLIENT_INFO['name']}/{CLIENT_INFO['version']}",
        }
        headers.update(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=self.timeout)
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")[:2000]
            raise HttpStatusError(err.code, dict(err.headers), body) from None
        with resp:
            sid = resp.headers.get("Mcp-Session-Id")
            if sid:
                self.session_id = sid
            if not expect_response:
                return None
            ctype = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", "replace")
        if "text/event-stream" in ctype:
            return self._from_sse(raw, payload.get("id"))
        if not raw.strip():
            raise RuntimeError("empty response body")
        msg = json.loads(raw)
        if isinstance(msg, list):
            msg = next((m for m in msg if m.get("id") == payload.get("id")), msg[0])
        return msg

    @staticmethod
    def _from_sse(raw, want_id):
        data_lines, events = [], []
        for line in raw.splitlines() + [""]:
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
            elif line == "" and data_lines:
                events.append("\n".join(data_lines))
                data_lines = []
        for event in events:
            try:
                msg = json.loads(event)
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("id") == want_id:
                return msg
        raise RuntimeError("no JSON-RPC response found in event stream")

    def request(self, method, params=None):
        self._id += 1
        msg = self._post({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}})
        if "error" in msg:
            raise RuntimeError(f"{method} failed: {json.dumps(msg['error'])[:500]}")
        return msg.get("result", {})

    def notify(self, method):
        try:
            self._post({"jsonrpc": "2.0", "method": method}, expect_response=False)
        except HttpStatusError:
            pass  # some servers reject the notification; listing usually still works

    def initialize(self):
        result = self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": CLIENT_INFO,
        })
        self.protocol_version = result.get("protocolVersion")
        self.notify("notifications/initialized")
        return result

    def list_tools(self, max_pages=50):
        tools, cursor = [], None
        for _ in range(max_pages):
            result = self.request("tools/list", {"cursor": cursor} if cursor else {})
            tools.extend(result.get("tools", []))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        return tools


def fetch_json(url, timeout):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": f"{CLIENT_INFO['name']}/{CLIENT_INFO['version']}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001 - discovery is best effort
        return None


def auth_report(url, headers, timeout):
    """Read OAuth discovery metadata after a 401. Best effort, never raises."""
    www = next((v for k, v in headers.items() if k.lower() == "www-authenticate"), "") or ""
    lines = [f"WWW-Authenticate: {www or '(missing)'}"]
    checks = []
    match = re.search(r'resource_metadata="([^"]+)"', www)
    parsed = urllib.parse.urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [match.group(1)] if match else []
    candidates += [f"{origin}/.well-known/oauth-protected-resource{parsed.path.rstrip('/')}",
                   f"{origin}/.well-known/oauth-protected-resource"]
    checks.append(("401 points at resource metadata (resource_metadata=)", bool(match)))
    prm, prm_url = None, None
    for cand in candidates:
        prm = fetch_json(cand, timeout)
        if isinstance(prm, dict):
            prm_url = cand
            break
    if not prm:
        checks.append(("protected resource metadata (RFC 9728) found", False))
        return lines, checks
    lines.append(f"Protected resource metadata: {prm_url}")
    checks.append(("protected resource metadata (RFC 9728) found", True))
    resource = prm.get("resource")
    checks.append((f"'resource' equals the server URL exactly ({resource})", resource == url))
    servers = prm.get("authorization_servers") or []
    if not servers:
        checks.append(("authorization_servers listed", False))
        return lines, checks
    issuer = servers[0]
    lines.append(f"Authorization server (first entry is the one Claude uses): {issuer}")
    ip = urllib.parse.urlparse(issuer)
    iorigin, ipath = f"{ip.scheme}://{ip.netloc}", ip.path.rstrip("/")
    asm = None
    for cand in (f"{iorigin}/.well-known/oauth-authorization-server{ipath}",
                 f"{iorigin}/.well-known/openid-configuration{ipath}",
                 f"{issuer.rstrip('/')}/.well-known/openid-configuration",
                 f"{iorigin}/.well-known/oauth-authorization-server"):
        asm = fetch_json(cand, timeout)
        if isinstance(asm, dict):
            lines.append(f"Authorization server metadata: {cand}")
            break
    if not isinstance(asm, dict):
        checks.append(("authorization server metadata reachable", False))
        return lines, checks
    pkce = asm.get("code_challenge_methods_supported") or []
    checks.append(("PKCE S256 advertised (code_challenge_methods_supported)", "S256" in pkce))
    dcr = bool(asm.get("registration_endpoint"))
    cimd = bool(asm.get("client_id_metadata_document_supported")) and \
        "none" in (asm.get("token_endpoint_auth_methods_supported") or [])
    kinds = [k for k, ok in (("DCR", dcr), ("CIMD", cimd)) if ok]
    checks.append((f"client registration without manual setup (DCR or CIMD): {', '.join(kinds) or 'neither'}",
                   bool(kinds)))
    scopes = (asm.get("scopes_supported") or []) + (prm.get("scopes_supported") or [])
    checks.append(("offline_access in scopes_supported (refresh tokens)", "offline_access" in scopes))
    return lines, checks


def tool_title(tool):
    ann = tool.get("annotations") or {}
    return (tool.get("title") or ann.get("title") or "").strip()


def analyse_tool(tool, all_names):
    name = tool.get("name", "")
    lname = name.lower()
    desc = tool.get("description") or ""
    ann = tool.get("annotations") or {}
    schema = tool.get("inputSchema") or {}
    flags = []

    if not tool_title(tool):
        flags.append("no-title")
    ro, de, ow = ann.get("readOnlyHint"), ann.get("destructiveHint"), ann.get("openWorldHint")
    if ro is None:
        flags.append("no-readonly-hint")
    if ro is not True and de is None:
        flags.append("no-destructive-hint")
    if ow is None:
        flags.append("no-openworld-hint")
    if ro is True and de is True:
        flags.append("hint-conflict")
    if re.search(READ_VERBS, lname) and not re.search(WRITE_VERBS, lname) and ro is not True:
        flags.append("read-name-not-readonly")
    if re.search(WRITE_VERBS, lname) and ro is True:
        flags.append("write-name-marked-readonly")
    if re.search(DELETE_VERBS, lname) and de is not True:
        flags.append("delete-name-not-destructive")

    others = [n for n in all_names if n != name and len(n) > 3]
    if any(re.search(r"(?<![\w\-])" + re.escape(n) + r"(?![\w\-])", desc) for n in others):
        flags.append("mentions-tool")
    if steers(desc):
        flags.append("steers-calls")
    if EXTERNAL_RE.search(desc):
        flags.append("external-instructions")
    if REST_RE.search(desc):
        flags.append("rest-path")

    props = schema.get("properties") if isinstance(schema, dict) else None
    prop_names = {k.lower() for k in props} if isinstance(props, dict) else set()
    free_body = any(isinstance(v, dict) and v.get("type") == "object" and not v.get("properties")
                    for v in (props or {}).values())
    if re.search(DISPATCH_NAMES, lname) or (prop_names & DISPATCH_ARGS and (free_body or "method" in prop_names
                                                                             or "operation" in prop_names
                                                                             or "tool_name" in prop_names)):
        flags.append("dispatcher")

    stoks = est_tokens(schema)
    depth = schema_depth(schema)
    if has_union(schema) or depth > 3 or stoks > SCHEMA_TOKEN_LIMIT:
        flags.append("mega-schema")
    if not desc.strip():
        flags.append("desc-missing")
    elif len(desc.strip()) < 40:
        flags.append("desc-thin")
    if len(name) > 64:
        flags.append("name-too-long")

    hints = "".join(c if v is not None else "-" for c, v in (("R", ro), ("D", de), ("I", ann.get("idempotentHint")), ("O", ow)))
    hint_vals = "".join(("1" if v else "0") if v is not None else "-" for v in (ro, de, ann.get("idempotentHint"), ow))
    return {
        "name": name,
        "title": tool_title(tool),
        "hints_declared": hints,
        "hints_values": hint_vals,
        "description_chars": len(desc),
        "schema_tokens": stoks,
        "schema_depth": depth,
        "definition_tokens": est_tokens(tool),
        "flags": flags,
    }


def print_table(rows, out):
    headers = ["tool", "title", "hints RDIO", "desc", "schema tok", "flags"]
    data = [[r["name"], "yes" if r["title"] else "NO", f'{r["hints_declared"]} {r["hints_values"]}',
             str(r["description_chars"]), str(r["schema_tokens"]), ", ".join(r["flags"]) or "-"] for r in rows]
    widths = [min(max(len(h), *(len(d[i]) for d in data)) if data else len(h), 48 if i == 0 else 200)
              for i, h in enumerate(headers)]
    fmt = "  ".join("{:<%d}" % w for w in widths[:-1]) + "  {}"
    out.write(fmt.format(*headers) + "\n")
    out.write(fmt.format(*["-" * w for w in widths[:-1]], "-" * 5) + "\n")
    for d in data:
        d[0] = d[0] if len(d[0]) <= 48 else d[0][:45] + "..."
        out.write(fmt.format(*d) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="List an MCP server's tools (initialize + tools/list only) and flag review risks.",
        epilog="Hints column: R=readOnlyHint D=destructiveHint I=idempotentHint O=openWorldHint; "
               "first group shows which are declared, second their values (1/0/-). Tokens are approximate (chars/4).")
    parser.add_argument("url", nargs="?", help="Streamable HTTP MCP endpoint, e.g. https://example.com/mcp")
    parser.add_argument("--token-env", metavar="VAR",
                        help="name of an environment variable holding a bearer token (the value is never printed)")
    parser.add_argument("--header", action="append", default=[], metavar="'Name: value'",
                        help="extra request header; repeatable. Prefer --token-env for secrets")
    parser.add_argument("--format", choices=["table", "json", "markdown"], default="table")
    parser.add_argument("--save-raw", metavar="PATH", help="write the raw tools/list result to PATH")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds per request (default 30)")
    parser.add_argument("--explain-flags", action="store_true", help="print what each flag means and exit")
    args = parser.parse_args()

    if args.explain_flags:
        for key, text in FLAG_HELP.items():
            print(f"{key:30} {text}")
        return 0
    if not args.url:
        parser.error("url is required")

    headers = {}
    for h in args.header:
        if ":" not in h:
            parser.error(f"bad --header {h!r}; use 'Name: value'")
        k, v = h.split(":", 1)
        headers[k.strip()] = v.strip()
    if args.token_env:
        token = os.environ.get(args.token_env)
        if not token:
            parser.error(f"environment variable {args.token_env} is empty or unset")
        headers["Authorization"] = f"Bearer {token}"

    client = McpClient(args.url, headers, args.timeout)
    try:
        init = client.initialize()
        tools = client.list_tools()
    except HttpStatusError as err:
        if err.status in (401, 403):
            print(f"Auth required: HTTP {err.status} from {args.url}. No tools were listed.")
            if not args.token_env:
                print("Re-run with --token-env VAR (bearer token in that env var) to list tools.")
            lines, checks = auth_report(args.url, err.headers, args.timeout)
            print("\nOAuth discovery (what directory reviewers' clients read):")
            for line in lines:
                print(f"  {line}")
            for label, ok in checks:
                print(f"  [{'pass' if ok else 'FAIL'}] {label}")
            return 2
        print(f"Error: HTTP {err.status} from {args.url}: {err.body[:300]}", file=sys.stderr)
        return 1
    except (urllib.error.URLError, OSError, RuntimeError, ValueError) as err:
        print(f"Error talking to {args.url}: {err}", file=sys.stderr)
        return 1

    if args.save_raw:
        with open(args.save_raw, "w", encoding="utf-8") as fh:
            json.dump({"initialize": init, "tools": tools}, fh, indent=2)

    names = [t.get("name", "") for t in tools]
    rows = [analyse_tool(t, names) for t in tools]
    instructions = init.get("instructions") or ""
    total_tokens = est_tokens({"tools": tools})
    server_flags = []
    if len(tools) > TOOL_COUNT_LIMIT:
        server_flags.append(f"too-many-tools: {len(tools)} > {TOOL_COUNT_LIMIT} (Google flags 'dozens of tools')")
    if total_tokens > TOTAL_TOKEN_LIMIT:
        server_flags.append(f"heavy-definitions: ~{total_tokens} tokens > {TOTAL_TOKEN_LIMIT}")
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        server_flags.append(f"duplicate-names: {', '.join(dupes)}")
    if not instructions.strip():
        server_flags.append("no-instructions: initialize returned no server instructions (Google registration requires them)")
    if steers(instructions):
        server_flags.append("instructions-steer-calls: server instructions tell the model to always/never call something")

    counts = {}
    for r in rows:
        for f in r["flags"]:
            counts[f] = counts.get(f, 0) + 1
    summary = {
        "url": args.url,
        "server": init.get("serverInfo", {}),
        "protocol_version": init.get("protocolVersion"),
        "tool_count": len(tools),
        "definition_tokens_total": total_tokens,
        "instructions_tokens": est_tokens(instructions) if instructions else 0,
        "server_flags": server_flags,
        "flag_counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
    }

    if args.format == "json":
        json.dump({"summary": summary, "tools": rows}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    out = sys.stdout
    info = summary["server"]
    out.write(f"Server: {info.get('name', '?')} {info.get('version', '')}  protocol {summary['protocol_version']}\n")
    out.write(f"Tools: {len(tools)}  definition tokens ~{total_tokens}  "
              f"server instructions ~{summary['instructions_tokens']} tokens\n")
    for f in server_flags:
        out.write(f"SERVER FLAG {f}\n")
    out.write("\n")
    if args.format == "markdown":
        out.write("| tool | title | hints RDIO | desc chars | schema tokens | flags |\n|---|---|---|---|---|---|\n")
        for r in rows:
            out.write(f"| `{r['name']}` | {'yes' if r['title'] else 'NO'} | {r['hints_declared']} {r['hints_values']} | "
                      f"{r['description_chars']} | {r['schema_tokens']} | {', '.join(r['flags']) or '-'} |\n")
    else:
        print_table(rows, out)
    if counts:
        out.write("\nFlag counts: " + ", ".join(f"{k} {v}" for k, v in summary["flag_counts"].items()) + "\n")
        out.write("Run with --explain-flags for what each flag means. Flags are heuristics: confirm each one.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
