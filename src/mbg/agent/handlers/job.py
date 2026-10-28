"""job.status, job.wait, job.cancel."""
from __future__ import annotations

from mbg.agent import runio
from mbg.agent.envelope import Result


def _finish(tool_id, run_dir, job, resd) -> Result:
    if resd is not None:
        r = Result.from_dict(resd)
        r.job = {"id": job.get("id"), "state": job.get("state")}
        return r
    r = Result(tool=tool_id, status="NOT RUN")
    r.job = {"id": job.get("id"), "state": job.get("state"), "stage": job.get("stage", "")}
    r.run_dir = runio.rel(run_dir)
    if job.get("state") in ("queued", "running"):
        r.summary = f"job {job.get('id')} running (stage: {job.get('stage') or 'starting'})"
        r.next = [f"mbg job wait {job.get('id')}"]
    else:
        r.fail_tool("JOB_" + str(job.get("state", "unknown")).upper(),
                    job.get("reason", f"job ended in state {job.get('state')}"),
                    log=runio.log_tail(run_dir / runio.LOG_FILE))
    return r


def status(args, ctx) -> Result:
    run_dir = runio.find_job(args["id"])
    job = runio.job_state(run_dir)
    resd = runio.read_json(run_dir / runio.RESULT_FILE) \
        if job.get("state") not in ("queued", "running") else None
    return _finish("job.status", run_dir, job, resd)


def wait(args, ctx) -> Result:
    run_dir = runio.find_job(args["id"])
    wait_s = args.get("wait_s")
    job, resd = runio.wait_job(run_dir, 540.0 if wait_s is None else float(wait_s))
    return _finish("job.wait", run_dir, job, resd)


def cancel(args, ctx) -> Result:
    run_dir = runio.find_job(args["id"])
    job = runio.cancel_job(run_dir)
    r = Result(tool="job.cancel", status="PASS" if job.get("state") == "cancelled" else "NOT RUN",
               summary=f"job {job.get('id')}: {job.get('state')}")
    r.job = {"id": job.get("id"), "state": job.get("state")}
    return r
