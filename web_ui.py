"""Small loopback-only web console for starting and watching agent runs."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import socket
import time
import subprocess
import sys
import threading
import uuid
import webbrowser


JOBS = {}
JOBS_LOCK = threading.Lock()


class ConsoleServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def key_configured():
    """Expose readiness only; never return credentials to the browser."""
    return bool((os.environ.get("GOOGLE_API_KEY", os.environ.get("GEMINI_API_KEY")) or "").strip())


def live_state(job, root):
    output = job["output"].read_text(encoding="utf-8", errors="replace")
    run_log = next((line[9:].strip() for line in output.splitlines() if line.startswith("Run log: ")), None)
    if not run_log:
        return {}, None
    directory = Path(run_log).resolve()
    if directory.parent != (root / "runs").resolve():
        raise ValueError("Run log is outside the runs directory")
    path = directory / "checkpoint.json"
    return (json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}), directory


def handoff_token(state):
    pending = state.get("pending") or {}
    if state.get("status") not in ("waiting_for_input", "waiting_for_approval"):
        return None
    return str(pending.get("step")) + ":" + pending.get("approval", {}).get("id", "question")


class Handler(BaseHTTPRequestHandler):
    server_version = "WishLocal/1.0"

    def log_message(self, *_args):
        pass

    def send_json(self, value, status=200):
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            return self.send_json({"error": "This console only accepts local requests"}, 403)
        if self.path in ("/", "/logo.svg"):
            path = self.server.root / ("ui.html" if self.path == "/" else "assets/logo.svg")
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8" if self.path == "/" else "image/svg+xml")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/config":
            return self.send_json({"key_configured": key_configured(), "ui_protocol": 2})
        if self.path == "/api/active":
            with JOBS_LOCK:
                identifier = next((key for key, job in JOBS.items() if job["status"] == "running"), None)
            return self.send_json({"id": identifier})
        if self.path == "/api/skills":
            skills = sorted(path.stem for path in (self.server.root / "skills").glob("*.md"))
            return self.send_json({"skills": skills})
        if self.path == "/api/runs":
            return self.send_json({"runs": self.run_summaries()})
        if self.path.startswith("/api/runs/"):
            identifier = self.path.removeprefix("/api/runs/").split("/")[0]
            with JOBS_LOCK:
                job = JOBS.get(identifier)
            if not job:
                return self.send_json({"error": "Run not found in this UI session"}, 404)
            try:
                state, directory = live_state(job, self.server.root)
            except (ValueError, OSError) as exc:
                return self.send_json({"error": "Cannot read live checkpoint: " + str(exc)}, 500)
            token = handoff_token(state)
            pending = state.get("pending") if token and token != job.get("answered") and job["status"] == "running" else None
            if self.path.endswith("/evidence"):
                relative = (pending or {}).get("approval", {}).get("evidence", {}).get("screenshot")
                if not relative or not directory:
                    return self.send_json({"error": "No pending approval screenshot"}, 404)
                path = (directory / relative).resolve()
                if not path.is_relative_to(directory / "screenshots") or path.suffix != ".png" or not path.is_file():
                    return self.send_json({"error": "Invalid screenshot path"}, 400)
                body = path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            output = job["output"].read_text(encoding="utf-8", errors="replace")[-12000:]
            if job.get("error"):
                output += "\nConsole error: " + job["error"]
            return self.send_json({"id": identifier, "run_id": directory.name if directory else job.get("run_id"),
                                   "status": state["status"] if pending else job["status"], "output": output,
                                   "active": job["status"] == "running", "pending": pending, "handoff_token": token,
                                   "elapsed": int(job.get("finished", time.time()) - job["started"])})
        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.headers.get("Host", "").split(":")[0] not in ("127.0.0.1", "localhost"):
            return self.send_json({"error": "This console only accepts local requests"}, 403)
        origin = self.headers.get("Origin")
        if origin and origin not in (f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}"):
            return self.send_json({"error": "Cross-origin requests are not allowed"}, 403)
        if self.path != "/api/run" and not re.fullmatch(r"/api/runs/[a-f0-9]{12}/respond", self.path):
            return self.send_json({"error": "Not found"}, 404)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 10000:
                raise ValueError("Task request must be between 1 and 10,000 bytes")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Task request must be a JSON object")
            if self.path.endswith("/respond"):
                identifier = self.path.split("/")[3]
                with JOBS_LOCK:
                    job = JOBS.get(identifier)
                    if not job or job["status"] != "running" or job["process"].poll() is not None:
                        return self.send_json({"error": "The live run has ended; use CLI resume if paused."}, 409)
                    state, _ = live_state(job, self.server.root)
                    token = handoff_token(state)
                    if not token or payload.get("token") != token or job.get("answered") == token:
                        return self.send_json({"error": "This handoff is stale or already answered."}, 409)
                    if state["status"] == "waiting_for_approval":
                        decision = payload.get("decision")
                        if decision not in ("approve", "reject"):
                            raise ValueError("Choose approve or reject")
                        answer = decision + " " + state["pending"]["approval"]["id"]
                    else:
                        answer = payload.get("answer")
                        if not isinstance(answer, str) or not answer.strip() or len(answer) > 4000 or any(c in answer for c in "\r\n\x00"):
                            raise ValueError("Enter a single-line answer between 1 and 4,000 characters")
                    job["process"].stdin.write((answer + "\n").encode("utf-8"))
                    job["process"].stdin.flush()
                    job["answered"] = token
                return self.send_json({"accepted": True})
            task = payload.get("task")
            if not isinstance(task, str) or not task.strip() or len(task) > 4000:
                raise ValueError("Enter a task between 1 and 4,000 characters")
            mode = payload.get("mode", "files")
            if mode not in ("files", "browser", "desktop"):
                raise ValueError("Choose a supported computer access mode")
            if not key_configured():
                return self.send_json({"error": "API key missing in the console environment. Stop the console, then run 'source ~/.bash_profile' and 'python main.py ui' from Git Bash and refresh this page."}, 503)
            command = [sys.executable, "-u", str(self.server.root / "main.py"), "run", task,
                       "--workspace", str(self.server.root / "workspace"),
                       "--max-run-tokens", "0", "--max-requests", "0",
                       "--max-steps", "0", "--max-image-requests", "0"]
            policy = payload.get("approval_policy")
            if policy:
                if not isinstance(policy, str):
                    raise ValueError("Approval policy must be a project-relative JSON path")
                policy_path = (self.server.root / policy).resolve()
                if not policy_path.is_relative_to(self.server.root.resolve()) or policy_path.suffix != ".json":
                    raise ValueError("Approval policy must be a JSON file inside the project")
                from approval import validate_policy
                validate_policy(json.loads(policy_path.read_text(encoding="utf-8")))
                command.extend(["--approval-policy", str(policy_path)])
            if payload.get("skill"):
                skill = payload["skill"]
                if not isinstance(skill, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", skill):
                    raise ValueError("Invalid skill selection")
                skill_path = self.server.root / "skills" / (skill + ".md")
                if not skill_path.is_file():
                    raise ValueError("Selected skill does not exist")
                command.extend(["--skill", skill])
            if mode == "browser":
                command.append("--browser")
            elif mode == "desktop":
                command.extend(["--desktop", "--vision"])
            if mode == "browser" and payload.get("vision"):
                command.append("--vision")
            if payload.get("record"):
                command.append("--record-screen")
            identifier = uuid.uuid4().hex[:12]
            output_path = self.server.root / "runs" / ("ui-" + identifier + ".log")
            child_env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            child_env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(self.server.root / ".playwright"))
            with JOBS_LOCK:
                if any(job["status"] == "running" for job in JOBS.values()):
                    return self.send_json({"error": "A task is already running in this console. Wait for it to finish before starting another."}, 409)
                with output_path.open("w", encoding="utf-8") as output:
                    proc = subprocess.Popen(command, cwd=self.server.root, stdout=output,
                                            stderr=subprocess.STDOUT, stdin=subprocess.PIPE,
                                            env=child_env,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                record = {"process": proc, "output": output_path, "status": "running",
                          "started": time.time(), "run_id": None}
                JOBS[identifier] = record
            threading.Thread(target=self.watch_job, args=(identifier,), daemon=True).start()
            return self.send_json({"id": identifier, "status": "running"}, 202)
        except (ValueError, OSError, json.JSONDecodeError) as exc:
            return self.send_json({"error": str(exc)}, 400)

    def watch_job(self, identifier):
        with JOBS_LOCK:
            job = JOBS[identifier]
        code = job["process"].wait()
        if job["process"].stdin:
            job["process"].stdin.close()
        output = job["output"].read_text(encoding="utf-8", errors="replace")
        run_log = next((line.removeprefix("Run log: ").strip() for line in output.splitlines()
                        if line.startswith("Run log: ")), None)
        final_status = "failed" if code else "succeeded"
        evidence_error = None
        run_id = None
        if run_log:
            run_dir = Path(run_log)
            run_id = run_dir.name
            checkpoint = run_dir / "checkpoint.json"
            if checkpoint.is_file():
                try:
                    saved_status = json.loads(checkpoint.read_text(encoding="utf-8"))["status"]
                    if code == 0:
                        final_status = saved_status if saved_status != "running" else "failed"
                except (OSError, json.JSONDecodeError, KeyError) as exc:
                    final_status = "failed"
                    evidence_error = "Could not read the run checkpoint: " + str(exc)
        with JOBS_LOCK:
            job["status"] = final_status
            job["run_id"] = run_id
            job["finished"] = time.time()
            job["error"] = evidence_error

    def run_summaries(self):
        runs = []
        for path in (self.server.root / "runs").iterdir():
            if not path.is_dir() or not (path / "result.json").is_file():
                continue
            try:
                result = json.loads((path / "result.json").read_text(encoding="utf-8"))
                checkpoint_path = path / "checkpoint.json"
                checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8")) if checkpoint_path.is_file() else {}
                runs.append({"id": path.name, "status": result.get("status", "unknown"),
                             "summary": result.get("summary", ""), "steps": checkpoint.get("steps"),
                             "updated": path.stat().st_mtime})
            except (OSError, json.JSONDecodeError):
                continue
        runs.sort(key=lambda item: item["updated"], reverse=True)
        return runs[:8]


def serve(root: Path):
    for relative in ("ui.html", "assets/logo.svg"):
        if not (root / relative).is_file():
            raise ValueError("Console asset not found: " + relative)
    try:
        server = ConsoleServer(("127.0.0.1", 8765), Handler)
    except OSError as exc:
        raise ValueError("Cannot start the console on port 8765. Stop the existing console with Ctrl+C in its original terminal, then try again. " + str(exc)) from exc
    server.root = root
    print("Wish local console: http://127.0.0.1:8765/")
    print("Browser cache for agent runs: " + os.environ.get("PLAYWRIGHT_BROWSERS_PATH", str(root / ".playwright")))
    print("Only this computer can connect. Press Ctrl+C to stop the console.")
    threading.Timer(0.5, lambda: webbrowser.open("http://127.0.0.1:8765/")).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        with JOBS_LOCK:
            for job in JOBS.values():
                if job["status"] == "running" and job["process"].stdin:
                    job["process"].stdin.close()
        server.server_close()
