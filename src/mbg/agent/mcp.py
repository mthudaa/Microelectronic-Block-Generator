"""``mbg mcp`` — the agent tools over the Model Context Protocol (stdio).

Zero dependencies: newline-delimited JSON-RPC 2.0 on stdin/stdout, which is
the MCP stdio transport. Implements ``initialize``, ``ping``, ``tools/list``
and ``tools/call``; everything else is answered "method not found".

Each ``tools/call`` runs ``python -m mbg <tool> --args-json ...`` as a child
process and returns its envelope. The server itself never imports gLayout,
so it starts instantly, switching PDK between calls is safe (gdsfactory's
global state lives and dies with the child), and a stuck tool can be killed
without taking the server down. Long tools return a job id after
``wait_s`` (default 50 s, under typical client timeouts); the agent then
calls the ``job`` tool.

Register it with any MCP client as the command ``scripts/mbg mcp`` (see
docs/ai_interface.md for per-harness snippets).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional

from mbg.agent import registry

PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MCP_WAIT_S = float(os.environ.get("MBG_MCP_WAIT_S", "50"))
CALL_TIMEOUT_S = 3600

INSTRUCTIONS = (
    "MBG: AI-native analog layout (gLayout + Magic/netgen/KLayout/ngspice). "
    "Every tool returns one JSON envelope: status (PASS|FAIL|PARTIAL|NOT RUN|"
    "NOT AVAILABLE), summary, metrics, artifacts (paths), issues (code, "
    "message, hint) and next (suggested calls). Start with `doctor`, then "
    "`pdk` (action=info) to see legal devices; check netlists with "
    "`netlist_check` before simulating or laying out. Long tools "
    "(layout_generate, verify, flow_run) may return job.state=running: call "
    "`job` with action=wait and the id. A design passes only when all four "
    "sign-off legs pass; post-layout metrics must meet the spec for tapeout.")


def _src_dir() -> str:
    import mbg
    from pathlib import Path
    return str(Path(mbg.__file__).resolve().parents[1])


def call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch one MCP tool call through the CLI; return the envelope dict."""
    tools = {t["name"]: t for t in registry.mcp_tools()}
    spec = tools.get(name)
    if spec is None:
        return _error_env(name, "UNKNOWN_TOOL", f"no tool named {name!r}",
                          "tools/list shows the available tools")
    args = dict(arguments or {})
    disp = spec["dispatch"]
    if None in disp:
        tool_id = disp[None]
    else:
        key = spec["key"]
        sel = args.pop(key, None)
        if sel not in disp:
            return _error_env(name, "USAGE", f"{key} must be one of {sorted(disp)}",
                              f"pass {key}")
        tool_id = disp[sel]
    tool = registry.get(tool_id)
    allowed = set(tool.schema.get("properties", {}))
    args = {k: v for k, v in args.items() if k in allowed or k == "wait_s"}
    argv = [sys.executable, "-m", "mbg", tool_id, "--args-json", json.dumps(args)]
    if tool.long and "wait_s" not in args:
        argv += ["--wait-s", str(MCP_WAIT_S)]
    env = dict(os.environ)
    env["PYTHONPATH"] = _src_dir() + (os.pathsep + env["PYTHONPATH"]
                                      if env.get("PYTHONPATH") else "")
    try:
        p = subprocess.run(argv, capture_output=True, text=True, env=env,
                           timeout=CALL_TIMEOUT_S, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return _error_env(tool_id, "TIMEOUT", f"no answer within {CALL_TIMEOUT_S} s")
    out = (p.stdout or "").strip().splitlines()
    for line in reversed(out):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return _error_env(tool_id, "NO_ENVELOPE", "the tool produced no JSON envelope",
                      log=((p.stderr or "") + (p.stdout or ""))[-1500:])


def _error_env(tool: str, code: str, message: str, hint: str = "",
               log: str = "") -> Dict[str, Any]:
    err = {"code": code, "message": message}
    if hint:
        err["hint"] = hint
    if log:
        err["log"] = log
    return {"schema": "mbg.result/1", "tool": tool, "ok": False,
            "status": "NOT RUN", "summary": f"{code}: {message}", "metrics": {},
            "artifacts": {}, "issues": [], "next": [], "error": err}


# ── JSON-RPC plumbing ─────────────────────────────────────────────────

def _response(mid, result=None, error=None) -> Dict[str, Any]:
    msg: Dict[str, Any] = {"jsonrpc": "2.0", "id": mid}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    return msg


def handle(msg: Dict[str, Any], state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One JSON-RPC message in, at most one response out."""
    method = msg.get("method")
    mid = msg.get("id")
    is_request = "id" in msg and method is not None
    params = msg.get("params") or {}
    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        state["version"] = version
        import mbg
        return _response(mid, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "mbg", "title": "Microelectronic Block Generator",
                           "version": mbg.__version__},
            "instructions": INSTRUCTIONS,
        })
    if method in ("notifications/initialized", "notifications/cancelled",
                  "initialized") or (method or "").startswith("notifications/"):
        return None
    if method == "ping":
        return _response(mid, {})
    if method == "tools/list":
        tools = [{"name": t["name"], "description": t["description"],
                  "inputSchema": t["inputSchema"]} for t in registry.mcp_tools()]
        return _response(mid, {"tools": tools})
    if method == "tools/call":
        name = params.get("name", "")
        env = call_tool(name, params.get("arguments") or {})
        text = json.dumps(env, separators=(",", ":"))
        result = {"content": [{"type": "text", "text": text}],
                  "isError": not env.get("ok", False)}
        if state.get("version", PROTOCOL_VERSIONS[-1]) >= "2025-06-18":
            result["structuredContent"] = env
        return _response(mid, result)
    if is_request:
        return _response(mid, error={"code": -32601, "message": f"method not found: {method}"})
    return None


def serve(stdin=None, stdout=None) -> int:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    state: Dict[str, Any] = {}
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            out = _response(None, error={"code": -32700, "message": "parse error"})
            stdout.write(json.dumps(out) + "\n")
            stdout.flush()
            continue
        batch = msg if isinstance(msg, list) else [msg]
        replies = []
        for m in batch:
            try:
                rep = handle(m, state)
            except Exception as e:                           # noqa: BLE001
                rep = _response(m.get("id"), error={"code": -32603,
                                                    "message": f"{type(e).__name__}: {e}"})
            if rep is not None:
                replies.append(rep)
        if not replies:
            continue
        payload = replies if isinstance(msg, list) else replies[0]
        stdout.write(json.dumps(payload) + "\n")
        stdout.flush()
    return 0
