"""Persistent one-shot jobs. A foreground worker dispatches each job at most once."""

from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

from state import exclusive_lock, save_json


def utc_now():
    return datetime.now(timezone.utc)


def schedule_time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() is None:
        raise ValueError("Schedule needs an explicit UTC offset, e.g. 2026-10-24T18:30:00+05:30")
    return parsed.astimezone(timezone.utc)


def enqueue(root, config, at=None, event_file=None, max_lateness=60):
    directory = Path(root) / "jobs"
    directory.mkdir(exist_ok=True)
    if (at is None) == (event_file is None):
        raise ValueError("Choose exactly one schedule time or event file")
    if at is not None:
        due = schedule_time(at)
        if due <= utc_now():
            raise ValueError("Schedule time must be in the future")
        trigger = {"kind": "schedule", "at": due.isoformat(), "max_lateness": max_lateness}
    else:
        path = Path(event_file).resolve()
        if path.exists():
            raise ValueError("Event marker already exists; choose a new filename to avoid firing on an old event")
        trigger = {"kind": "file", "path": str(path)}
    job = {"version": 1, "id": uuid4().hex[:12], "status": "queued", "created_at": utc_now().isoformat(),
           "trigger": trigger, "config": config}
    save_json(directory / f"{job['id']}.json", job)
    return job


def dispatch_due(root, execute):
    """Caller owns worker lock. Claim before execution; never replay running/failed jobs."""
    directory = Path(root) / "jobs"
    for path in sorted(directory.glob("*.json")):
        job = json.loads(path.read_text(encoding="utf-8"))
        if job["status"] != "queued":
            continue
        trigger = job["trigger"]
        if trigger["kind"] == "schedule":
            lateness = (utc_now() - schedule_time(trigger["at"])).total_seconds()
            if lateness < 0:
                continue
            if lateness > trigger["max_lateness"]:
                job.update(status="missed", error="Worker reached the schedule after its allowed lateness")
                save_json(path, job)
                print(f"Job {job['id']}: missed schedule")
                continue
        elif not Path(trigger["path"]).is_file():
            continue
        from harness import RunLog
        log = RunLog(Path(root) / "runs")
        job.update(status="running", run_id=log.directory.name, started_at=utc_now().isoformat())
        save_json(path, job)
        print(f"Job {job['id']}: starting run {job['run_id']}")
        try:
            code = execute(job["config"], log)
            result_file = log.directory / "result.json"
            result = json.loads(result_file.read_text(encoding="utf-8")) if result_file.exists() else {}
            job["status"] = result.get("status", "failed") if code == 0 else "failed"
            job["exit_code"] = code
        except BaseException as exc:
            job.update(status="interrupted", error=str(exc) or type(exc).__name__)
            save_json(path, job)
            raise
        job["ended_at"] = utc_now().isoformat()
        save_json(path, job)
        print(f"Job {job['id']}: {job['status']}")


def worker(root, execute, once=False):
    directory = Path(root) / "jobs"
    directory.mkdir(exist_ok=True)
    with exclusive_lock(directory / "worker.lock"):
        while True:
            dispatch_due(root, execute)
            if once:
                return
            time.sleep(1)
