"""``mbg`` — the command line every agent harness can drive.

    mbg tools                         what can I call? (compact)
    mbg tools layout.generate         one tool's full input schema
    mbg doctor                        what works on this machine?
    mbg pdk info --section devices    what is legal in this PDK?
    mbg netlist check amp.spice       is my netlist sound?
    mbg sim run amp.spice --analysis op --supplies '{"VDD":3.3,"VSS":0}'
    mbg layout generate amp.spice     SPICE -> GDS + DRC/LVS/PEX
    mbg layout view <run_dir>         the layout as text
    mbg job wait <id>                 collect a long run
    mbg mcp                           the same tools over MCP (stdio)

Every command prints exactly ONE JSON document on stdout (see
:mod:`mbg.agent.envelope`); logs go to ``<run_dir>/log.txt``. Arguments come
from flags generated from each tool's JSON schema (``--supplies``,
``--wait-s`` ...), from ``--args-json '{...}'``, or from ``--args @file.json``.
Numbers accept SPICE suffixes (``20u``, ``1p``, ``3.3``). The exit code
mirrors the status: 0 PASS, 1 FAIL/PARTIAL, 2 usage, 3 NOT RUN/NOT
AVAILABLE, 4 still running.
"""
from __future__ import annotations

import json
import os
import re
import signal
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mbg.agent import registry, runio
from mbg.agent.envelope import EXIT_USAGE, Result

CLI_WAIT_S = 540.0
DEFAULT_JOB_TIMEOUT_S = 4 * 3600


# ── run context handed to every handler ───────────────────────────────

@dataclass
class Ctx:
    tool: registry.Tool
    run_dir: Optional[Path] = None
    design: Optional[str] = None
    log: Optional[Path] = None
    in_job: bool = False
    _stage: str = field(default="", repr=False)

    def path(self, name: str) -> Path:
        if self.run_dir is None:
            raise RuntimeError(f"{self.tool.id} has no run directory")
        return self.run_dir / name

    def workspace(self) -> Optional[Path]:
        return runio.out_root() / self.design if self.design else None

    def stage(self, text: str) -> None:
        """Report progress; visible through `mbg job status`."""
        self._stage = text
        print(f"[STAGE] {text}", flush=True)
        if self.in_job and self.run_dir is not None:
            runio.mark_job(self.run_dir, stage=text)


# ── value parsing ─────────────────────────────────────────────────────

_SI = {"t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3, "u": 1e-6,
       "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18}
_NUM_RE = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*"
                     r"(meg|[tgkmunpfa])?[a-zA-Z]*\s*$", re.IGNORECASE)


def parse_number(text: Any) -> float:
    """``20u`` -> 2e-05, ``1meg`` -> 1e6, ``3.3`` -> 3.3 (SPICE suffix rules)."""
    if isinstance(text, (int, float)):
        return float(text)
    m = _NUM_RE.match(str(text))
    if not m:
        raise ValueError(f"not a number: {text!r}")
    val = float(m.group(1))
    suf = (m.group(2) or "").lower()
    return val * _SI.get(suf, 1.0)


def _coerce(name: str, schema: Dict[str, Any], raw: Any) -> Any:
    typ = schema.get("type")
    types = typ if isinstance(typ, list) else [typ]
    if raw is None:
        return None
    if "boolean" in types:
        if isinstance(raw, bool):
            return raw
        return str(raw).lower() in ("1", "true", "yes", "on")
    if "integer" in types:
        return int(parse_number(raw))
    if "number" in types:
        return parse_number(raw)
    if "array" in types:
        vals = raw if isinstance(raw, list) else [raw]
        if len(vals) == 1 and isinstance(vals[0], str) and vals[0].strip().startswith("["):
            vals = json.loads(vals[0])
        item = (schema.get("items") or {}).get("type")
        if item in ("number", "integer"):
            return [parse_number(v) for v in vals]
        return [str(v) for v in vals]
    if "object" in types:
        if isinstance(raw, dict):
            return raw
        s = str(raw).strip()
        if s.startswith("@"):
            return json.loads(Path(s[1:]).read_text())
        if s.startswith("{"):
            return json.loads(s)
        if "string" in types:
            return s                   # a path or a keyword; the handler decides
        if s.endswith(".json") and Path(s).is_file():
            return json.loads(Path(s).read_text())
        raise ValueError(f"--{name.replace('_', '-')} expects a JSON object, "
                         f"@file.json or a .json path, got {s!r}")
    return raw if isinstance(raw, str) else str(raw)


class UsageError(ValueError):
    pass


def parse_args(tool: registry.Tool, argv: List[str]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Flags + positionals -> (tool arguments, global options)."""
    props = tool.schema.get("properties", {})
    positional = list(tool.schema.get("x-positional", []))
    opts: Dict[str, Any] = {"pretty": False, "verbose": False, "inline": False,
                            "wait_s": None, "help": False}
    raw: Dict[str, Any] = {}
    i = 0
    pos_vals: List[str] = []
    while i < len(argv):
        tok = argv[i]
        if tok in ("-h", "--help"):
            opts["help"] = True
            i += 1
            continue
        if tok in ("--pretty", "--verbose", "--inline"):
            opts[tok[2:]] = True
            i += 1
            continue
        if tok.startswith("--"):
            key, eq, val = tok[2:].partition("=")
            name = key.replace("-", "_")
            if name in ("args_json", "args"):
                if not eq:
                    i += 1
                    val = argv[i] if i < len(argv) else ""
                text = Path(val[1:]).read_text() if val.startswith("@") else val
                try:
                    raw.update(json.loads(text))
                except ValueError as e:
                    raise UsageError(f"--{key}: invalid JSON ({e})")
                i += 1
                continue
            if name.startswith("no_") and props.get(name[3:], {}).get("type") == "boolean":
                raw[name[3:]] = False
                i += 1
                continue
            if name == "wait_s" and "wait_s" not in props:
                opts["wait_s"] = parse_number(val if eq else argv[i + 1])
                i += 1 if eq else 2
                continue
            if name not in props:
                raise UsageError(
                    f"unknown option --{key} for `{tool.cli}`. Options: "
                    + " ".join(f"--{p.replace('_', '-')}" for p in props))
            typ = props[name].get("type")
            if typ == "boolean" and not eq:
                raw[name] = True
                i += 1
                continue
            if typ == "array" and not eq:
                vals = []
                i += 1
                while i < len(argv) and not argv[i].startswith("--"):
                    vals.append(argv[i])
                    i += 1
                raw[name] = vals
                continue
            if not eq:
                if i + 1 >= len(argv):
                    raise UsageError(f"--{key} needs a value")
                val = argv[i + 1]
                i += 2
            else:
                i += 1
            raw[name] = val
            continue
        pos_vals.append(tok)
        i += 1
    if len(pos_vals) > len(positional):
        raise UsageError(f"unexpected argument(s) {pos_vals[len(positional):]} for "
                         f"`{tool.cli}`")
    for name, val in zip(positional, pos_vals):
        raw.setdefault(name, val)
    args: Dict[str, Any] = {}
    for name, val in raw.items():
        if name not in props:
            raise UsageError(f"unknown argument {name!r} for `{tool.cli}`")
        try:
            args[name] = _coerce(name, props[name], val)
        except (ValueError, OSError) as e:
            raise UsageError(str(e))
        enum = props[name].get("enum")
        if enum and args[name] not in enum:
            raise UsageError(f"--{name.replace('_', '-')} must be one of {enum}, "
                             f"got {args[name]!r}")
    if "wait_s" in args and tool.long:
        opts["wait_s"] = args.pop("wait_s")      # a property of the call, not the work
    return args, opts


def missing_required(tool: registry.Tool, args: Dict[str, Any]) -> List[str]:
    return [r for r in tool.schema.get("required", []) if args.get(r) in (None, "")]


def usage_text(tool: registry.Tool) -> str:
    props = tool.schema.get("properties", {})
    req = set(tool.schema.get("required", []))
    pos = tool.schema.get("x-positional", [])
    head = tool.cli + "".join(f" <{p}>" for p in pos)
    lines = [head, "", "  " + tool.summary, ""]
    for name, p in props.items():
        typ = p.get("type")
        typ = "/".join(typ) if isinstance(typ, list) else typ
        flag = f"--{name.replace('_', '-')}"
        star = " (required)" if name in req else ""
        lines.append(f"  {flag:<16} {typ:<14} {p.get('description', '')}{star}")
    if tool.long:
        lines.append(f"  {'--wait-s':<16} {'number':<14} seconds to wait before returning a job id")
    lines += ["", "  Global: --args-json '{...}' | --args @file.json | --pretty | --verbose"]
    for ex in tool.examples:
        lines.append(f"  e.g. {ex}")
    return "\n".join(lines)


# ── executing a tool ──────────────────────────────────────────────────

def _needs_run_dir(tool: registry.Tool, args: Dict[str, Any]) -> bool:
    if tool.stage is None:
        return False
    return not tool.light or bool(args.get("design"))


def execute(tool: registry.Tool, args: Dict[str, Any], *,
            wait_s: Optional[float] = None, inline: bool = False) -> Result:
    """Run a tool and return its envelope. Never raises for tool errors."""
    t0 = time.monotonic()
    try:
        design = args.get("design")
        stage = tool.stage
        if stage == "pre_simulation" and args.get("post_layout"):
            stage = "post_simulation"
        run_dir = (runio.new_run_dir(tool.id, design, stage if design else None)
                   if _needs_run_dir(tool, args) else None)
    except (OSError, ValueError) as e:
        r = Result(tool=tool.id)
        r.fail_tool("BAD_WORKSPACE", str(e),
                    hint="mbg design init <name> creates a workspace")
        return r

    if tool.long and not inline:
        job = runio.start_job(tool.id, args, run_dir, DEFAULT_JOB_TIMEOUT_S)
        job, resd = runio.wait_job(run_dir, CLI_WAIT_S if wait_s is None else wait_s)
        if resd is not None:
            r = Result.from_dict(resd)
            r.job = {"id": job["id"], "state": job.get("state")}
            return r
        r = Result(tool=tool.id, status="NOT RUN")
        state = job.get("state")
        r.job = {"id": job["id"], "state": state, "stage": job.get("stage", "")}
        r.run_dir = runio.rel(run_dir)
        if state in ("queued", "running"):
            r.summary = (f"still running after {wait_s if wait_s is not None else CLI_WAIT_S:g}s "
                         f"(stage: {job.get('stage') or 'starting'}); the work continues "
                         f"in the background")
            r.next = [f"mbg job wait {job['id']}"]
        else:
            r.fail_tool("JOB_FAILED", job.get("reason", f"job ended in state {state}"),
                        log=runio.log_tail(run_dir / runio.LOG_FILE))
        r.elapsed_s = time.monotonic() - t0
        return r

    ctx = Ctx(tool=tool, run_dir=run_dir, design=args.get("design"))
    if run_dir is not None:
        ctx.log = run_dir / runio.LOG_FILE
        log_path = ctx.log
        tmp = None
    else:
        tmp = tempfile.NamedTemporaryFile(prefix="mbg-", suffix=".log", delete=False)
        tmp.close()
        log_path = Path(tmp.name)
    r = _call_handler(tool, args, ctx, log_path)
    if tmp is not None:
        if r.ok:
            os.unlink(tmp.name)
        else:
            r.artifacts.setdefault("log", tmp.name)
    if run_dir is not None:
        r.run_dir = r.run_dir or runio.rel(run_dir)
        r.artifacts.setdefault("log", runio.rel(log_path))
        _write_result(run_dir, r)
    r.elapsed_s = time.monotonic() - t0
    return r


def _call_handler(tool, args, ctx, log_path: Path) -> Result:
    try:
        handler = registry.load_handler(tool)
    except Exception as e:
        r = Result(tool=tool.id)
        return r.fail_tool("UNAVAILABLE", f"{type(e).__name__}: {e}",
                           hint="run `mbg doctor` to see what is missing")
    try:
        with runio.captured(log_path):
            r = handler(args, ctx)
    except UsageError as e:
        r = Result(tool=tool.id)
        r.fail_tool("USAGE", str(e), hint=f"mbg {tool.id.replace('.', ' ')} --help")
    except FileNotFoundError as e:
        r = Result(tool=tool.id)
        r.fail_tool("NOT_FOUND", str(e))
    except Exception as e:
        r = Result(tool=tool.id)
        tb = traceback.format_exc()
        try:
            with open(log_path, "a") as f:
                f.write(tb)
        except OSError:
            pass
        r.fail_tool("EXCEPTION", f"{type(e).__name__}: {e}",
                    log=runio.log_tail(log_path, 12))
    if not isinstance(r, Result):
        bad = Result(tool=tool.id)
        return bad.fail_tool("BAD_HANDLER", f"handler returned {type(r).__name__}")
    return r


def _write_result(run_dir: Path, r: Result) -> None:
    try:
        (run_dir / runio.RESULT_FILE).write_text(json.dumps(r.to_dict(max_issues=500),
                                                            indent=2))
    except OSError:
        pass


def job_main(run_dir_s: str) -> int:
    """Entry point of a detached job process (`python -m mbg _job <run_dir>`)."""
    run_dir = Path(run_dir_s)
    req = runio.read_json(run_dir / runio.REQUEST_FILE) or {}
    tool = registry.get(req.get("tool", ""))
    t0 = time.monotonic()
    if tool is None:
        runio.mark_job(run_dir, state="failed", reason="unknown tool in request")
        return 2
    runio.mark_job(run_dir, state="running", pid=os.getpid())

    def _timeout(signum, frame):
        raise TimeoutError(f"job exceeded {req.get('timeout_s')} s")

    def _term(signum, frame):
        raise KeyboardInterrupt("cancelled")

    signal.signal(signal.SIGALRM, _timeout)
    signal.signal(signal.SIGTERM, _term)
    signal.alarm(int(req.get("timeout_s") or DEFAULT_JOB_TIMEOUT_S))
    args = req.get("args", {})
    ctx = Ctx(tool=tool, run_dir=run_dir, design=args.get("design"),
              log=run_dir / runio.LOG_FILE, in_job=True)
    state = "done"
    try:
        r = tool and registry.load_handler(tool)(args, ctx)
        if not isinstance(r, Result):
            r = Result(tool=tool.id).fail_tool("BAD_HANDLER", "handler returned no Result")
    except TimeoutError as e:
        r = Result(tool=tool.id).fail_tool("TIMEOUT", str(e),
                                           log=runio.log_tail(ctx.log))
        state = "failed"
    except KeyboardInterrupt:
        r = Result(tool=tool.id).fail_tool("CANCELLED", "job was cancelled")
        state = "cancelled"
    except Exception as e:
        traceback.print_exc()
        r = Result(tool=tool.id).fail_tool("EXCEPTION", f"{type(e).__name__}: {e}",
                                           log=runio.log_tail(ctx.log, 12))
        state = "failed"
    finally:
        signal.alarm(0)
    r.run_dir = r.run_dir or runio.rel(run_dir)
    r.artifacts.setdefault("log", runio.rel(ctx.log))
    r.elapsed_s = time.monotonic() - t0
    _write_result(run_dir, r)
    import datetime as _dt
    runio.mark_job(run_dir, state=state, status=r.status,
                   finished=_dt.datetime.now().isoformat(timespec="seconds"))
    return 0


# ── top level ─────────────────────────────────────────────────────────

def _emit(r: Result, pretty: bool) -> int:
    sys.stdout.write(r.to_json(pretty=pretty) + "\n")
    sys.stdout.flush()
    return r.exit_code()


def _usage_error(tool_id: str, message: str, hint: str = "") -> int:
    r = Result(tool=tool_id)
    r.fail_tool("USAGE", message, hint=hint or "mbg tools")
    return _emit(r, False)


def _resolve(argv: List[str]) -> Tuple[Optional[registry.Tool], List[str]]:
    if not argv:
        return None, argv
    if "." in argv[0] and registry.get(argv[0]):
        return registry.get(argv[0]), argv[1:]
    if len(argv) >= 2 and registry.get(f"{argv[0]}.{argv[1]}"):
        return registry.get(f"{argv[0]}.{argv[1]}"), argv[2:]
    if registry.get(argv[0]):
        return registry.get(argv[0]), argv[1:]
    return None, argv


def top_help() -> str:
    lines = ["mbg — AI-native analog layout tools (gLayout + Magic/netgen/KLayout/ngspice)",
             "",
             "Every command prints one JSON envelope on stdout: "
             "{status: PASS|FAIL|PARTIAL|NOT RUN|NOT AVAILABLE, summary, metrics, "
             "artifacts, issues, next}.",
             "Start with `mbg doctor`, then `mbg tools` for the input schemas.", ""]
    for group, tools in registry.groups().items():
        for t in tools:
            lines.append(f"  {t.cli[4:]:<18} {t.summary.split('. ')[0]}")
    lines += ["", "  tools [<id>] [--format json|md]   list tools / one tool's schema",
              "  mcp                              serve the same tools over MCP (stdio)",
              "  version", ""]
    return "\n".join(lines)


def _tools_command(argv: List[str]) -> int:
    fmt = "json"
    pretty = "--pretty" in argv
    rest = [a for a in argv if a != "--pretty"]
    if "--format" in rest:
        k = rest.index("--format")
        fmt = rest[k + 1] if k + 1 < len(rest) else "json"
        rest = rest[:k] + rest[k + 2:]
    if fmt == "md":
        from mbg.agent.docs import tools_markdown
        sys.stdout.write(tools_markdown())
        return 0
    r = Result(tool="tools", status="PASS")
    if rest:
        t = registry.get(rest[0]) or _resolve(rest)[0]
        if t is None:
            return _usage_error("tools", f"unknown tool {rest[0]!r}")
        r.summary = t.summary
        r.data = {"tool": t.as_dict()}
        return _emit(r, pretty)
    r.summary = (f"{len(registry.TOOLS)} tools; `mbg tools <id>` for one input schema. "
                 f"Long tools run as jobs: collect with `mbg job wait <id>`.")
    r.data = {"tools": [{"id": t.id, "cli": t.cli, "summary": t.summary,
                         "required": t.schema.get("required", []),
                         "positional": t.schema.get("x-positional", []),
                         "long": t.long} for t in registry.TOOLS]}
    r.next = ["mbg doctor", "mbg pdk info --section devices"]
    return _emit(r, pretty)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "help"):
        sys.stdout.write(top_help())
        return 0
    head = argv[0]
    if head == "tools":
        return _tools_command(argv[1:])
    if head == "mcp":
        from mbg.agent.mcp import serve
        return serve()
    if head == "_job":
        return job_main(argv[1])
    if head in ("version", "--version"):
        import mbg
        r = Result(tool="version", status="PASS", summary=f"mbg {mbg.__version__}")
        r.metrics = {"version": mbg.__version__}
        return _emit(r, "--pretty" in argv)
    if head == "check":
        argv = ["doctor"] + argv[1:]
    tool, rest = _resolve(argv)
    if tool is None:
        group = [t.id for t in registry.TOOLS if t.group == head]
        hint = (f"`{head}` needs an action: {', '.join(group)}" if group
                else "mbg tools lists every command")
        return _usage_error(head, f"unknown command {' '.join(argv[:2])!r}", hint)
    try:
        args, opts = parse_args(tool, rest)
    except UsageError as e:
        return _usage_error(tool.id, str(e), f"mbg {tool.id.replace('.', ' ')} --help")
    if opts["help"]:
        sys.stdout.write(usage_text(tool) + "\n")
        return 0
    miss = missing_required(tool, args)
    if miss:
        return _usage_error(tool.id, f"missing required argument(s): {miss}",
                            f"mbg {tool.id.replace('.', ' ')} --help")
    r = execute(tool, args, wait_s=opts["wait_s"], inline=opts["inline"])
    code = _emit(r, opts["pretty"])
    if opts["verbose"] and r.run_dir:
        log = Path(r.run_dir) / runio.LOG_FILE
        if log.is_file():
            sys.stderr.write(log.read_text(errors="replace"))
    return code
