"""Portable, offline evidence viewer and explicit submission-folder export."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
from uuid import uuid4

from state import save_json


def asset_path(directory, relative):
    if not isinstance(relative, str) or "\\" in relative or ":" in relative:
        raise ValueError(f"Invalid evidence path: {relative!r}")
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or not name.parts:
        raise ValueError(f"Invalid evidence path: {relative!r}")
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError(f"Evidence path leaves run directory: {relative}")
    return path


def read_run(directory):
    directory = Path(directory).resolve(strict=True)
    events = []
    for number, line in enumerate((directory / "events.jsonl").read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid events.jsonl at line {number}; inspect the interrupted log") from exc
        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
            raise ValueError(f"Invalid event at line {number}")
        events.append(event)
    result_path = directory / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
    assets = set()
    warnings = []
    started, stopped = set(), set()
    steps_with_images = set()
    for event in events:
        payload = event.get("result", {}) if event["event"] == "tool_result" else event
        for key in ("screenshot", "video"):
            relative = payload.get(key)
            if relative:
                path = asset_path(directory, relative)
                if path.is_file():
                    assets.add(relative)
                    if key == "screenshot":
                        steps_with_images.add(event.get("step"))
                else:
                    warnings.append(f"Missing {key}: {relative}")
        if event["event"] == "recording_started":
            started.add(event["video"])
        if event["event"] == "recording_stopped":
            stopped.add(event["video"])
        if event["event"] == "recording_failed":
            warnings.append("Recording failed: " + str(event.get("error")))
        if event["event"] == "browser_session_failed":
            warnings.append("Browser session save/close failed: " + str(event.get("error")))
    if not started:
        warnings.append("No whole-run screen recording was started for this run.")
    if started - stopped:
        warnings.append("Unfinalized video segments: " + ", ".join(sorted(started - stopped)))
    if len(started) > 1:
        warnings.append("Recording has separate segments. Time between detached processes is not recorded.")
    missing = sorted({e["step"] for e in events if e["event"] == "tool_call"} - steps_with_images)
    if missing:
        warnings.append("No screenshot for tool steps: " + ", ".join(map(str, missing)))
    if not result:
        warnings.append("No final result.json; the run may have been interrupted before saving an outcome.")
    return {"run_id": directory.name, "events": events, "result": result,
            "assets": sorted(assets), "warnings": list(dict.fromkeys(warnings))}


def write_viewer(directory, data=None):
    directory = Path(directory)
    data = read_run(directory) if data is None else data
    # Escape '<' even in JSON strings so logged page/file text cannot end the script tag.
    serialized = json.dumps(data, ensure_ascii=True).replace("<", "\\u003c")
    page = Path(__file__).with_name("replay.html").read_text(encoding="utf-8")
    destination = directory / "replay.html"
    destination.write_text(page.replace("__RUN_DATA__", serialized), encoding="utf-8")
    return destination


def export_run(directory, export_root, artifacts=()):
    directory = Path(directory).resolve(strict=True)
    data = read_run(directory)
    artifact_paths = [Path(path).resolve(strict=True) for path in artifacts]
    if any(not path.is_file() for path in artifact_paths):
        raise ValueError("Each --artifact must be a file")
    destination = Path(export_root) / f"{directory.name}-{uuid4().hex[:8]}"
    destination.mkdir(parents=True, exist_ok=False)
    # A failed export is deliberately left inspectable; only manifest.json marks completion.
    for name in ["events.jsonl"] + (["result.json"] if (directory / "result.json").is_file() else []) + data["assets"]:
        source = asset_path(directory, name)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    skills = [e for e in data["events"] if e["event"] == "skill_loaded"]
    for index, skill in enumerate(skills, 1):
        target = destination / "skills" / f"{index:03d}.md"
        target.parent.mkdir(exist_ok=True)
        target.write_text(skill["content"], encoding="utf-8")
    data["artifacts"] = []
    for index, source in enumerate(artifact_paths, 1):
        relative = f"artifacts/{index:03d}-{source.name}"
        target = destination / relative
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(source, target)
        data["artifacts"].append(relative)
    write_viewer(destination, data)
    (destination / "README.txt").write_text(
        "Open replay.html in a browser. This folder works offline; keep its subfolders together.\n"
        "Exports contain task text, file contents, user answers, screenshots and any recorded screen.\n"
        "Review before sharing. API environment variables/configuration are not exported.\n"
        "Task success is not certification of submission requirements. Ticket/PNR evidence and\n"
        "an external phone recording must be supplied separately when required by the PS.\n"
        "Video segments do not cover detached gaps. Missing evidence is listed in the viewer.\n"
        "manifest.json lists SHA-256/size for every exported file except itself.\n", encoding="utf-8")
    files = []
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            files.append({"path": path.relative_to(destination).as_posix(), "bytes": path.stat().st_size, "sha256": digest})
    save_json(destination / "manifest.json", {
        "version": 1, "run_id": directory.name, "created_at": datetime.now(timezone.utc).isoformat(),
        "warnings": data["warnings"], "files": files,
    })
    return destination
