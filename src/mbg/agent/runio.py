"""Run directories, output capture and background jobs for the agent tools.

Three problems an agent hits when it drives an EDA flow through a shell or
MCP, and how this module answers them:

* **Noisy output.** The layout flow prints hundreds of progress lines and
  Magic/netgen add their own. :func:`captured` redirects the process-level
  file descriptors 1 and 2 into ``<run_dir>/log.txt`` — Python prints, C
  library output and inherited subprocess output alike — so the only thing
  that reaches the agent is the JSON envelope.
* **Where did it go?** Every call gets a run directory. Inside a design
  workspace (``--design NAME``) it is the stage directory of the AGENTS.md
  artifact layout (``outputs/<name>/lvs/`` ...); otherwise
  ``outputs/runs/<timestamp>-<tool>-<id>/``. Nothing is overwritten: a
  second run of a stage gets ``lvs-2/``.
* **Calls that outlive a tool timeout.** Shell tools in agent harnesses
  time out after a few minutes and MCP clients sooner. Long tools run as a
  detached job (:func:`start_job`); the call waits up to ``wait_s`` and,
  if the job is still going, returns its id so the agent can
  ``mbg job wait <id>`` instead of losing the work.
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import json
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

JOB_FILE = "job.json"
REQUEST_FILE = "request.json"
RESULT_FILE = "result.json"
LOG_FILE = "log.txt"


# ── locations ─────────────────────────────────────────────────────────

def out_root() -> Path:
    """Where runs and design workspaces live.

    ``$MBG_OUT`` if set; inside the repository, its gitignored ``outputs/``;
    anywhere else, ``./mbg-out`` so a user-wide install never writes into
    someone else's tree unasked.
    """
    env = os.environ.get("MBG_OUT")
    if env:
        return Path(env).expanduser().resolve()
    from mbg.config import repo_root
    repo = repo_root().resolve()
    cwd = Path.cwd().resolve()
    if cwd == repo or repo in cwd.parents:
        return repo / "outputs"
    return cwd / "mbg-out"


def rel(path: Any) -> str:
    """A path as short as possible for the agent: relative to cwd when inside it."""
    if path is None:
        return ""
    p = Path(path).resolve()
    try:
        return str(p.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(p)


def safe_name(name: str) -> str:
    """Validate a design/workspace name: one path component, no traversal."""
    if not name or name in (".", "..") or "/" in name or "\\" in name \
            or name.startswith(".") or len(name) > 120:
        raise ValueError(f"invalid name {name!r}: use letters, digits, '-', '_' "
                         f"(one path component, no '/', no leading '.')")
    return name


def new_run_dir(tool_id: str, design: Optional[str] = None,
                stage: Optional[str] = None) -> Path:
    if design:
        base = out_root() / safe_name(design)
        if not base.is_dir():
            raise FileNotFoundError(
                f"design workspace {design!r} does not exist under {rel(out_root())}; "
                f"create it with: mbg design init {design}")
        name = stage or tool_id.replace(".", "_")
        cand = base / name
        n = 2
        while cand.exists() and any(cand.iterdir()):
            cand = base / f"{name}-{n}"
            n += 1
    else:
        stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        cand = out_root() / "runs" / f"{stamp}-{tool_id.replace('.', '_')}-{secrets.token_hex(2)}"
    cand.mkdir(parents=True, exist_ok=True)
    return cand


# ── output capture ────────────────────────────────────────────────────

@contextlib.contextmanager
def captured(log_path: Path) -> Iterator[int]:
    """Send fd 1 and fd 2 to ``log_path``; yield a dup of the real stdout.

    Done at the descriptor level, not by swapping ``sys.stdout``: Magic,
    netgen and ngspice are subprocesses that inherit fd 1, and gdsfactory
    logs from C extensions. Swapping the Python object would leave all of
    that on the agent's screen.
    """
    sys.stdout.flush()
    sys.stderr.flush()
    real_out = os.dup(1)
    real_err = os.dup(2)
    fd = os.open(str(log_path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        yield real_out
    finally:
        try:
            sys.stdout.flush()
            sys.stderr.flush()
        except Exception:
            pass
        os.dup2(real_out, 1)
        os.dup2(real_err, 2)
        os.close(fd)
        os.close(real_err)
        os.close(real_out)


def log_tail(log_path: Path, lines: int = 15) -> str:
    try:
        text = Path(log_path).read_text(errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(text[-lines:])


# ── jobs ──────────────────────────────────────────────────────────────

def _jobs_index() -> Path:
    d = out_root() / ".jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _src_dir() -> str:
    import mbg
    return str(Path(mbg.__file__).resolve().parents[1])


def start_job(tool_id: str, args: Dict[str, Any], run_dir: Path,
              timeout_s: int) -> Dict[str, Any]:
    """Launch ``python -m mbg _job <run_dir>`` detached; return the job record."""
    # outputs/runs/<id>/ -> "<id>";  outputs/<design>/<stage>/ -> "<design>.<stage>"
    job_id = (run_dir.name if run_dir.parent.name == "runs"
              else f"{run_dir.parent.name}.{run_dir.name}")
    _write_json(run_dir / REQUEST_FILE, {"tool": tool_id, "args": args,
                                         "timeout_s": timeout_s})
    job = {"id": job_id, "tool": tool_id, "state": "queued",
           "run_dir": str(run_dir), "timeout_s": timeout_s,
           "started": _dt.datetime.now().isoformat(timespec="seconds")}
    _write_json(run_dir / JOB_FILE, job)
    (_jobs_index() / job_id).write_text(str(run_dir))
    env = dict(os.environ)
    env["PYTHONPATH"] = _src_dir() + (os.pathsep + env["PYTHONPATH"]
                                      if env.get("PYTHONPATH") else "")
    log = open(run_dir / LOG_FILE, "ab")
    proc = subprocess.Popen([sys.executable, "-m", "mbg", "_job", str(run_dir)],
                            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                            cwd=os.getcwd(), env=env, start_new_session=True)
    log.close()
    job["pid"] = proc.pid
    job["state"] = "running"
    _write_json(run_dir / JOB_FILE, job)
    return job


def find_job(job_id: str) -> Path:
    """Resolve a job id (or a run directory) to its run directory."""
    p = Path(job_id)
    if p.is_dir() and (p / JOB_FILE).is_file():
        return p
    if "/" in job_id or job_id.startswith("."):
        raise FileNotFoundError(f"no job at {job_id!r}")
    idx = _jobs_index() / job_id
    if idx.is_file():
        return Path(idx.read_text().strip())
    raise FileNotFoundError(f"unknown job id {job_id!r}")


def _alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    # A zombie (finished, not reaped) still answers kill(0).
    try:
        with open(f"/proc/{pid}/stat") as f:
            return f.read().split()[2] != "Z"
    except OSError:
        return True


def job_state(run_dir: Path) -> Dict[str, Any]:
    job = read_json(run_dir / JOB_FILE) or {"state": "unknown"}
    if job.get("state") == "running" and not _alive(job.get("pid")) \
            and not (run_dir / RESULT_FILE).exists():
        job["state"] = "failed"
        job["reason"] = "the job process exited without writing a result (see log.txt)"
    return job


def wait_job(run_dir: Path, wait_s: float) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """Poll until the job finishes or ``wait_s`` elapses."""
    deadline = time.monotonic() + max(0.0, wait_s)
    while True:
        job = job_state(run_dir)
        if job.get("state") not in ("queued", "running"):
            return job, read_json(run_dir / RESULT_FILE)
        if time.monotonic() >= deadline:
            return job, None
        time.sleep(0.5)


def cancel_job(run_dir: Path) -> Dict[str, Any]:
    job = job_state(run_dir)
    pid = job.get("pid")
    if job.get("state") in ("queued", "running") and pid:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
        job["state"] = "cancelled"
        job["finished"] = _dt.datetime.now().isoformat(timespec="seconds")
        _write_json(run_dir / JOB_FILE, job)
    return job


def mark_job(run_dir: Path, **fields: Any) -> None:
    job = read_json(run_dir / JOB_FILE) or {}
    job.update(fields)
    _write_json(run_dir / JOB_FILE, job)
