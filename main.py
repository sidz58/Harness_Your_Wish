"""CLI entry point: python main.py --help."""

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4

from gemini import Gemini, ProviderError
from harness import Agent, RunError, RunLog
from tools import MAX_FILE_BYTES, Toolbox
from state import exclusive_lock, save_json


ROOT = Path(__file__).resolve().parent


def load_skill(name):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError("Skill name must contain lowercase letters, digits, underscores, or hyphens; omit .md")
    directory = (ROOT / "skills").resolve(strict=True)
    path = (directory / f"{name}.md").resolve()
    if not path.is_relative_to(directory):
        raise ValueError("Skill path leaves the skills directory")
    if not path.is_file():
        raise ValueError(f"Skill not found: {name}. Run 'python main.py skills' to list available skills")
    with path.open("rb") as source:
        data = source.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"Skill exceeds {MAX_FILE_BYTES} bytes")
    content = data.decode("utf-8")
    if not content.strip():
        raise ValueError(f"Skill is empty: {name}")
    skill = {"name": name, "content": content, "sha256": hashlib.sha256(data).hexdigest()}
    normalized_content = content.replace("\r\n", "\n")
    if normalized_content.startswith("---\n"):
        header = normalized_content.split("---", 2)[1]
        metadata = re.search(r"^metadata:([^\n]*)$", header, re.MULTILINE)
        if metadata:
            try:
                skill["metadata"] = json.loads(metadata.group(1))
            except json.JSONDecodeError as exc:
                raise ValueError("Skill metadata must be a JSON object on one line") from exc
            if not isinstance(skill["metadata"], dict):
                raise ValueError("Skill metadata must be a JSON object on one line")
    return skill


class ScriptedDemo:
    """Explicit offline fixture exercising the real loop and real tools; not an AI."""

    name, model = "scripted-offline-demo", "none"

    def generate(self, contents, declarations, instruction):
        previous = [part["functionResponse"]["response"]
                    for item in contents for part in item["parts"] if "functionResponse" in part]
        if any(not result["ok"] for result in previous):
            raise RunError("Scripted demo encountered a tool failure; inspect events.jsonl")
        stage = len(previous)
        if stage == 0:
            name, args = "list_files", {"path": ".", "reason": "Inspect the demo workspace"}
        elif stage == 1:
            name, args = "read_file", {"path": "notes.txt", "reason": "Read the source notes"}
        elif stage == 2:
            name, args = "run_command", {"command": "python_version", "reason": "Check the available Python runtime"}
        elif stage == 3:
            report = "# Offline tool demonstration\n\n" + previous[1]["content"] + "\nRuntime: " + previous[2]["stdout"].strip() + "\n"
            name, args = "write_file", {"path": "report.md", "content": report, "reason": "Save a report using observed tool outputs"}
        elif stage == 4:
            name, args = "read_file", {"path": "report.md", "reason": "Read back the saved report"}
        elif stage == 5:
            name, args = "finish", {"summary": "Scripted demo wrote and verified report.md; no model API was called.",
                                   "evidence_steps": [previous[4]["step"], previous[2]["step"]],
                                   "reason": "Report contents and runtime output were observed"}
        else:
            raise RunError("Scripted demo exceeded its defined sequence")
        return {"role": "model", "parts": [{"functionCall": {"name": name, "args": args}}]}, {"totalTokenCount": 0}


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("Must be positive")
    return number


def run_limit(value):
    if value.lower() == "unlimited":
        return 0
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("Must be non-negative; use 0 or unlimited for no run budget")
    return number


def main(argv=None, queued_config=None, queued_log=None):
    parser = argparse.ArgumentParser(description="Alum Track: general computer agent")
    sub = parser.add_subparsers(dest="mode", required=True)
    demo = sub.add_parser("demo", help="Run the scripted offline demonstration; no API key or network needed")
    demo.add_argument("--record-screen", action="store_true", help="Record the Windows primary screen locally")
    sub.add_parser("ui", help="Open the local task console in your browser")
    sub.add_parser("skills", help="List the Markdown skills available in this project")
    live = sub.add_parser("run", help="Run a task through the Gemini API")
    live.add_argument("task", help="Task in natural language")
    live.add_argument("--workspace", type=Path, default=ROOT / "workspace")
    live.add_argument("--model", default="gemini-3.5-flash-lite")
    live.add_argument("--commands", type=Path, help="JSON object mapping command names to fixed executable/argument lists")
    live.add_argument("--skill", help="Skill name from skills/, without the .md extension")
    live.add_argument("--browser", action="store_true", help="Enable an isolated Chromium browser")
    live.add_argument("--browser-only", action="store_true", help="Expose browser, handoff and task outcome tools; requires --browser and excludes --desktop")
    live.add_argument("--source-url", help="Lock list extraction to this exact URL and disable freeform writes/commands; requires --browser, excludes --desktop")
    live.add_argument("--extract-count", type=positive_int, help="Require this exact extraction count (1..100); requires --source-url")
    live.add_argument("--approval-policy", type=Path, help="JSON rules selecting browser actions that require explicit approval")
    live.add_argument("--vision", action="store_true", help="Send browser screenshots to the model")
    live.add_argument("--desktop", action="store_true", help="Enable Windows desktop mouse/keyboard and vision")
    live.add_argument("--record-screen", action="store_true", help="Record the Windows primary screen and save every-step screenshots locally")
    live.add_argument("--max-image-bytes", type=positive_int, default=2 * 1024 * 1024)
    live.add_argument("--max-image-requests", type=run_limit, default=0,
                      help="Image-bearing request ceiling; 0 or unlimited disables it (default: unlimited)")
    live.add_argument("--headless", action="store_true", help="Hide the browser window (requires --browser)")
    live.add_argument("--max-requests", type=run_limit, default=0,
                      help="Model request ceiling; 0 or unlimited disables it (default: unlimited)")
    live.add_argument("--max-steps", type=run_limit, default=0,
                      help="Tool action ceiling; 0 or unlimited disables it (default: unlimited)")
    live.add_argument("--max-run-tokens", type=run_limit, default=0,
                      help="Total reported token ceiling; 0 or unlimited disables it (default: unlimited)")
    live.add_argument("--max-output-tokens", type=positive_int, default=2048)
    live.add_argument("--request-timeout", type=positive_int, default=45)
    live.add_argument("--min-request-interval", type=float, default=0.5,
                      help="Minimum seconds between API request starts (default: 0.5; 0 disables pacing)")
    live.add_argument("--command-timeout", type=positive_int, default=15)
    live.add_argument("--detach-on-handoff", action="store_true", help="Save a pending question and exit; answer later with resume")
    scheduled = sub.add_parser("schedule", parents=[live], add_help=False, help="Queue a one-shot run at an offset-aware time")
    scheduled.add_argument("--at", required=True)
    scheduled.add_argument("--max-lateness", type=positive_int, default=60, help="Skip if worker is later by more than these seconds")
    event = sub.add_parser("on-event", parents=[live], add_help=False, help="Queue a one-shot run when a new marker file appears")
    event.add_argument("--event-file", type=Path, required=True)
    worker_parser = sub.add_parser("worker", help="Run queued jobs; keep this terminal open")
    worker_parser.add_argument("--once", action="store_true")
    sub.add_parser("jobs", help="List queued job status and run IDs")
    status_parser = sub.add_parser("status", help="Inspect a durable run")
    status_parser.add_argument("run_id")
    replay_parser = sub.add_parser("replay", help="Generate an offline HTML viewer for a stopped run")
    replay_parser.add_argument("run_id")
    export_parser = sub.add_parser("export", help="Export a stopped run's evidence to exports/")
    export_parser.add_argument("run_id")
    export_parser.add_argument("--artifact", type=Path, action="append", default=[], help="Explicit additional evidence file; repeat as needed")
    resume = sub.add_parser("resume", help="Continue a saved run without replaying old actions")
    resume.add_argument("run_id")
    resume.add_argument("--answer")
    resume.add_argument("--note", help="Describe the outcome of an uncertain interrupted action")
    decisions = resume.add_mutually_exclusive_group()
    decisions.add_argument("--approve", metavar="APPROVAL_ID", help="Approve only the exact pending action and page state")
    decisions.add_argument("--reject", metavar="APPROVAL_ID", help="Reject the pending action and cancel the run; no model request")
    resume.add_argument("--fresh-browser", action="store_true", help="Explicitly discard saved browser storage for this resume")
    for option in ("max-requests", "max-steps", "max-image-requests", "max-run-tokens"):
        resume.add_argument("--" + option, type=run_limit, default=None,
                            help="New total ceiling, including previous usage; 0 or unlimited removes it")
    args = argparse.Namespace(**queued_config) if queued_config is not None else parser.parse_args(argv)
    browser = None
    desktop = None
    recorder = None
    stack = ExitStack()
    resume_state = None
    answer = note = None
    decision = None
    fresh_browser = False
    log = queued_log
    try:
        if args.mode == "ui":
            from web_ui import serve
            serve(ROOT)
            return 0
        if args.mode == "worker":
            from jobs import worker
            worker(ROOT, lambda config, job_log: main([], queued_config=config, queued_log=job_log), once=args.once)
            return 0
        if args.mode == "jobs":
            for path in sorted((ROOT / "jobs").glob("*.json")):
                job = json.loads(path.read_text(encoding="utf-8"))
                print(f"{job['id']}  {job['status']}  run={job.get('run_id', '-')}  {job['trigger']}")
            return 0
        if args.mode in {"resume", "status", "replay", "export"}:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
                raise ValueError("Use the run ID, not a path")
            directory = (ROOT / "runs" / args.run_id).resolve(strict=True)
            if directory.parent != (ROOT / "runs").resolve():
                raise ValueError("Run path leaves runs directory")
            if args.mode == "status":
                state = json.loads((directory / "checkpoint.json").read_text(encoding="utf-8"))
                print(json.dumps({key: state[key] for key in ("status", "requests", "steps", "tokens", "pending", "error")}, indent=2))
                if state.get("failure"):
                    print("Failure details: " + json.dumps(state["failure"], ensure_ascii=False))
                return 0
            stack.enter_context(exclusive_lock(directory / "run.lock"))
            if args.mode in {"replay", "export"}:
                from replay import write_viewer, export_run
                path = write_viewer(directory) if args.mode == "replay" else export_run(directory, ROOT / "exports", args.artifact)
                print(f"Evidence: {path}")
                viewer = path if args.mode == "replay" else path / "replay.html"
                print(f'Open in Git Bash: explorer.exe "{viewer.resolve().as_posix()}"')
                print("Review the contents before sharing.")
                return 0
            resume_state = json.loads((directory / "checkpoint.json").read_text(encoding="utf-8"))
            if resume_state["status"] in {"succeeded", "cancelled"}:
                raise ValueError("This run already succeeded or was cancelled")
            if (directory / "STOP").exists():
                raise ValueError("Emergency STOP file still exists. Review the run and remove it yourself before resuming")
            config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
            answer, note = args.answer, args.note
            decision = ("approve", args.approve) if args.approve else ("reject", args.reject) if args.reject else None
            fresh_browser = args.fresh_browser
            for key in ("max_requests", "max_steps", "max_run_tokens", "max_image_requests"):
                if getattr(args, key) is not None:
                    config[key] = getattr(args, key)
            pending = resume_state.get("pending")
            from approval import validate_decision
            validate_decision(pending, decision)
            awaiting_approval = bool(pending and pending.get("approval", {}).get("status") == "pending")
            if decision and (answer is not None or note is not None):
                raise ValueError("Use an approval decision by itself, without --answer or --note")
            if decision and decision[0] == "reject":
                from approval import reject_pending
                outcome = reject_pending(RunLog.reopen(directory), resume_state, decision)
                print(outcome["summary"])
                return 0
            if awaiting_approval and fresh_browser:
                raise ValueError("Cannot approve with --fresh-browser; reject the pending action or restore its saved session")
            if pending and pending["name"] == "ask_user" and not (answer and answer.strip()):
                raise ValueError("Pending question: " + pending["arguments"]["question"] + "; provide --answer")
            if pending and not awaiting_approval and pending["name"] != "ask_user" and not (note and note.strip()):
                raise ValueError("Interrupted action outcome is uncertain. Inspect it and provide --note; no automatic replay")
            args = argparse.Namespace(**config)
            log = RunLog.reopen(directory)
            print("Resuming with fresh evidence. Browser storage and the last URL will be restored unless --fresh-browser was selected. Unsaved page memory is not restored.")
        if args.mode in {"schedule", "on-event"}:
            from jobs import enqueue
            config = {action.dest: getattr(args, action.dest) for action in live._actions if action.dest != "help"}
            config.update(mode="run", workspace=str(args.workspace.resolve(strict=True)),
                          commands=None, _commands=json.loads(args.commands.read_text(encoding="utf-8")) if args.commands else None,
                          _skill=load_skill(args.skill) if args.skill else None, detach_on_handoff=True)
            from approval import validate_policy
            config["_approval_policy"] = validate_policy(json.loads(args.approval_policy.read_text(encoding="utf-8"))) if args.approval_policy else None
            config["approval_policy"] = None
            if config["_approval_policy"] is not None and not args.browser:
                raise ValueError("--approval-policy requires --browser")
            if args.source_url:
                from browser import Browser
                config["source_url"] = Browser.canonical_url(args.source_url)
                if not args.browser or args.desktop:
                    raise ValueError("--source-url requires --browser and cannot enable --desktop")
            if args.extract_count is not None and (not args.source_url or args.extract_count > 100):
                raise ValueError("--extract-count requires --source-url and must be 1..100")
            Toolbox(config["workspace"], config["_commands"], config["command_timeout"])
            if (ROOT / "runs").resolve().is_relative_to(Path(config["workspace"])):
                raise ValueError("Choose a workspace that does not contain the runs directory")
            if config["min_request_interval"] < 0 or (args.headless and not args.browser) or (args.vision and not (args.browser or args.desktop)) or (args.record_screen and args.headless) or (args.browser_only and (not args.browser or args.desktop)):
                raise ValueError("Invalid run options")
            job = enqueue(ROOT, config, at=args.at if args.mode == "schedule" else None,
                          event_file=args.event_file if args.mode == "on-event" else None,
                          max_lateness=args.max_lateness if args.mode == "schedule" else 60)
            print(f"Queued job {job['id']}: {job['trigger']}. Start 'python main.py worker' and keep it running.")
            return 0
        if args.mode == "run" and args.min_request_interval < 0:
            raise ValueError("--min-request-interval cannot be negative")
        if args.mode == "run" and getattr(args, "browser_only", False) and (not args.browser or args.desktop):
            raise ValueError("--browser-only requires --browser and cannot be combined with --desktop")
        if args.mode == "run" and getattr(args, "source_url", None):
            from browser import Browser
            args.source_url = Browser.canonical_url(args.source_url)
            if not args.browser or args.desktop:
                raise ValueError("--source-url requires --browser and cannot enable --desktop")
        if args.mode == "run" and getattr(args, "extract_count", None) is not None and (not getattr(args, "source_url", None) or args.extract_count > 100):
            raise ValueError("--extract-count requires --source-url and must be 1..100")
        if args.mode == "run" and args.headless and not args.browser:
            raise ValueError("--headless requires --browser")
        if args.mode == "run" and args.vision and not (args.browser or args.desktop):
            raise ValueError("--vision requires --browser or --desktop")
        if args.mode == "run" and getattr(args, "record_screen", False) and args.headless:
            raise ValueError("--record-screen cannot record a hidden browser; omit --headless")
        if args.mode == "skills":
            for path in sorted((ROOT / "skills").iterdir()):
                if path.is_file() and path.suffix == ".md":
                    print(path.stem)
            return 0
        skill = (getattr(args, "_skill", None) if hasattr(args, "_skill") else load_skill(args.skill) if args.skill else None) if args.mode == "run" else None
        if resume_state is not None:
            skill = resume_state["skill"]
        if args.mode == "demo":
            print("SCRIPTED OFFLINE DEMO: real tools, predefined actions, no AI or API requests.")
            workspace = ROOT / "workspace" / ("demo-" + uuid4().hex[:8])
            workspace.mkdir(parents=True, exist_ok=False)
            (workspace / "notes.txt").write_text(
                "Project: general computer agent\nFirst milestone: file tools, terminal tools, and a verified agent loop.\n",
                encoding="utf-8")
            provider, commands, limits = ScriptedDemo(), None, {}
            command_timeout = 15
            task = "Create report.md containing the notes and observed Python version, then verify it."
        else:
            provider = Gemini(os.environ.get("GOOGLE_API_KEY", os.environ.get("GEMINI_API_KEY")), args.model,
                              args.request_timeout, args.max_output_tokens)
            workspace = Path(args.workspace).resolve(strict=True)
            commands = getattr(args, "_commands", None) if hasattr(args, "_commands") else json.loads(Path(args.commands).read_text(encoding="utf-8")) if args.commands else None
            limits = {"max_requests": args.max_requests, "max_steps": args.max_steps,
                      "browser_only": getattr(args, "browser_only", False),
                      "source_url": getattr(args, "source_url", None), "extract_count": getattr(args, "extract_count", None),
                      "max_run_tokens": args.max_run_tokens, "vision": args.vision,
                      "max_image_bytes": args.max_image_bytes, "max_image_requests": args.max_image_requests,
                      "min_request_interval": args.min_request_interval, "detach_on_handoff": args.detach_on_handoff}
            from approval import validate_policy
            policy_file = getattr(args, "approval_policy", None)
            if hasattr(args, "_approval_policy"):
                policy = args._approval_policy
            elif policy_file:
                policy = json.loads(Path(policy_file).read_text(encoding="utf-8"))
            else:
                policy = None
            if policy is not None:
                validate_policy(policy)
            if policy is not None and not args.browser:
                raise ValueError("--approval-policy requires --browser")
            limits["approval_policy"] = policy
            command_timeout, task = args.command_timeout, args.task
        if (ROOT / "runs").resolve().is_relative_to(workspace.resolve()):
            raise ValueError("Choose a workspace that does not contain the runs directory")
        toolbox = Toolbox(workspace, commands, command_timeout)
        log = log or RunLog(ROOT / "runs")
        if resume_state is None:
            stack.enter_context(exclusive_lock(log.directory / "run.lock"))
        if args.mode == "run":
            config = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
            config.update(workspace=str(workspace), commands=None, _commands=commands, _skill=skill)
            config.update(approval_policy=None, _approval_policy=policy)
            save_json(log.directory / "config.json", config)
        print(f"Workspace: {workspace}\nRun log: {log.directory}")
        if args.mode == "run":
            print("Run limits: " + ", ".join(f"{name}={value or 'unlimited'}" for name, value in
                  (("tokens", args.max_run_tokens), ("requests", args.max_requests),
                   ("steps", args.max_steps), ("image requests", args.max_image_requests)))
                  + f"; minimum API request interval: {args.min_request_interval}s")
        if skill:
            print(f"Skill: {skill['name']}")
        if (args.mode == "run" and (args.browser or args.desktop)) or getattr(args, "record_screen", False):
            stack.enter_context(exclusive_lock(ROOT / "runs" / "computer.lock"))
        if getattr(args, "record_screen", False):
            from recording import ScreenRecorder
            print("SCREEN RECORDING: capturing the primary monitor locally, including other visible windows. No audio. Keep the screen unlocked.")
            try:
                recorder = ScreenRecorder(log)
            except (Exception, KeyboardInterrupt) as exc:
                log.record("recording_failed", error=str(exc) or type(exc).__name__)
                raise
            print(f"Recording: {recorder.video}")
        if args.mode == "run" and args.browser:
            from browser import Browser
            try:
                browser = Browser(log.directory, headless=args.headless, restore=resume_state is not None and not fresh_browser)
            except Exception as exc:
                raise RunError(f"Browser startup failed: {exc}") from exc
        if args.mode == "run" and args.desktop:
            from desktop import Desktop
            desktop = Desktop(log.directory)
            print("DESKTOP CONTROL: primary monitor screenshots will be sent to the model. "
                  "Press F12 or move the pointer to a screen corner to stop. Keep the desktop unlocked.")
            print(f"Emergency stop file: {desktop.stop_file}")
        outcome = Agent(provider, toolbox, log, skill=skill, browser=browser, desktop=desktop, recorder=recorder, **limits).run(task, resume_state=resume_state, answer=answer, note=note, decision=decision)
        if recorder is not None:
            recorder.close()
        print(outcome["summary"])
        print(f"Requests: {outcome['requests']}; reported tokens: {outcome['tokens']}")
        if outcome["status"] == "waiting_for_input":
            print(f'Answer later: python main.py resume {log.directory.name} --answer "your answer"')
        if outcome["status"] == "waiting_for_approval":
            pending = json.loads((log.directory / "checkpoint.json").read_text(encoding="utf-8"))["pending"]
            identifier = pending["approval"]["id"]
            print(f"Approve: python main.py resume {log.directory.name} --approve {identifier}")
            print(f"Reject:  python main.py resume {log.directory.name} --reject {identifier}")
        return 0
    except (ValueError, OSError, ProviderError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Run interrupted.", file=sys.stderr)
        return 130
    finally:
        cleanup_failed = False
        try:
            try:
                if recorder is not None:
                    recorder.close()
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                cleanup_failed = True
            finally:
                if desktop is not None:
                    desktop.close()
                if browser is not None:
                    try:
                        browser.close()
                    except Exception as exc:
                        print(f"ERROR: Browser session save/close failed: {exc}", file=sys.stderr)
                        log.record("browser_session_failed", error=str(exc))
                        cleanup_failed = True
        finally:
            stack.close()
        if cleanup_failed:
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
