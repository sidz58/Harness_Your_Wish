"""Local console checks; no model calls or real child agent processes."""

from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
import io
import os
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import web_ui


class ConsoleTests(unittest.TestCase):
    def test_console_port_cannot_be_shared_by_another_server(self):
        server = web_ui.ConsoleServer(("127.0.0.1", 0), web_ui.Handler)
        try:
            with self.assertRaises(OSError):
                duplicate = ThreadingHTTPServer(server.server_address, web_ui.Handler)
                duplicate.server_close()
        finally:
            server.server_close()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        for name in ("assets", "skills", "runs"):
            (self.root / name).mkdir()
        source = Path(web_ui.__file__).parent
        shutil.copyfile(source / "ui.html", self.root / "ui.html")
        shutil.copyfile(source / "assets/logo.svg", self.root / "assets/logo.svg")
        (self.root / "skills/runtime_report.md").write_text("Report the runtime", encoding="utf-8")
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web_ui.Handler)
        self.server.root = self.root
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        web_ui.JOBS.clear()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        web_ui.JOBS.clear()
        self.directory.cleanup()

    def request(self, path, data=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET" if data is None else "POST", path,
                           None if data is None else json.dumps(data),
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        status, body = response.status, response.read()
        connection.close()
        return status, body

    def test_readiness_and_logo_never_expose_key(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "not-a-real-key"}, clear=True):
            status, body = self.request("/api/config")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body), {"key_configured": True, "ui_protocol": 2})
            self.assertNotIn(b"not-a-real-key", body)
        status, body = self.request("/logo.svg")
        self.assertEqual(status, 200)
        self.assertEqual(body, (self.root / "assets/logo.svg").read_bytes())
        self.assertEqual(self.request("/assets/../web_ui.py")[0], 404)

    def test_missing_key_rejects_before_launch_or_log(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(web_ui.subprocess, "Popen") as child:
            status, body = self.request("/api/run", {"task": "Check Python"})
            self.assertEqual(status, 503)
            self.assertIn("Git Bash", json.loads(body)["error"])
            child.assert_not_called()
            self.assertEqual(list((self.root / "runs").iterdir()), [])

    def test_underscore_skill_and_handoff_flags_reach_child(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "not-a-real-key"}, clear=True), \
                patch.object(web_ui.subprocess, "Popen") as child, \
                patch.object(web_ui.Handler, "watch_job"):
            status, body = self.request("/api/run", {"task": "Check Python", "skill": "runtime_report"})
            self.assertEqual(status, 202, body)
            argv = child.call_args.args[0]
            self.assertIn("runtime_report", argv)
            self.assertNotIn("--detach-on-handoff", argv)
            for flag in ("--max-run-tokens", "--max-requests", "--max-steps", "--max-image-requests"):
                self.assertEqual(argv[argv.index(flag) + 1], "0")
            self.assertEqual(child.call_args.kwargs["stdin"], web_ui.subprocess.PIPE)
            self.assertEqual(child.call_args.kwargs["env"]["PYTHONIOENCODING"], "utf-8")
            self.assertEqual(child.call_args.kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"], str(self.root / ".playwright"))
            self.assertEqual(self.request("/api/run", {"task": "Another task"})[0], 409)

    def test_explicit_browser_cache_is_preserved(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "not-a-real-key", "PLAYWRIGHT_BROWSERS_PATH": "custom-cache"}, clear=True), \
                patch.object(web_ui.subprocess, "Popen") as child, \
                patch.object(web_ui.Handler, "watch_job"):
            status, body = self.request("/api/run", {"task": "Open a page", "mode": "browser"})
            self.assertEqual(status, 202, body)
            self.assertIn("--browser", child.call_args.args[0])
            self.assertEqual(child.call_args.kwargs["env"]["PLAYWRIGHT_BROWSERS_PATH"], "custom-cache")

    def pending_job(self, approval=False):
        directory = self.root / "runs/live"
        directory.mkdir()
        pending = {"step": 3, "name": "ask_user", "arguments": {"question": "Filename?"}}
        if approval:
            pending.update(name="browser_click", arguments={"role": "button", "name": "Confirm"},
                           approval={"id": "decision123", "evidence": {"url": "http://localhost/"}})
        state = {"status": "waiting_for_approval" if approval else "waiting_for_input", "pending": pending}
        (directory / "checkpoint.json").write_text(json.dumps(state), encoding="utf-8")
        output = self.root / "runs/ui-live.log"
        output.write_text("Run log: " + str(directory) + "\n", encoding="utf-8")
        process = Mock()
        process.poll.return_value = None
        process.stdin = io.BytesIO()
        identifier = "abcdef123456"
        web_ui.JOBS[identifier] = {"process": process, "output": output, "status": "running", "started": 0}
        return identifier, process

    def test_live_question_reconnect_answer_and_duplicate_rejection(self):
        identifier, process = self.pending_job()
        self.assertEqual(json.loads(self.request('/api/active')[1])["id"], identifier)
        state = json.loads(self.request('/api/runs/' + identifier)[1])
        self.assertTrue(state["active"])
        self.assertEqual(state["status"], "waiting_for_input")
        endpoint = '/api/runs/' + identifier + '/respond'
        self.assertEqual(self.request(endpoint, {"token": "old", "answer": "x"})[0], 409)
        self.assertEqual(self.request(endpoint, {"token": state["handoff_token"], "answer": "x\ny"})[0], 400)
        payload = {"token": state["handoff_token"], "answer": "note.txt"}
        self.assertEqual(self.request(endpoint, payload)[0], 200)
        self.assertEqual(self.request(endpoint, payload)[0], 409)
        self.assertEqual(process.stdin.getvalue(), b"note.txt\n")
        self.assertIsNone(json.loads(self.request('/api/runs/' + identifier)[1])["pending"])

    def test_approval_requires_explicit_decision_bound_to_pending_id(self):
        identifier, process = self.pending_job(approval=True)
        endpoint = '/api/runs/' + identifier + '/respond'
        payload = {"token": "3:decision123", "answer": "yes"}
        self.assertEqual(self.request(endpoint, payload)[0], 400)
        payload["decision"] = "reject"
        self.assertEqual(self.request(endpoint, payload)[0], 200)
        self.assertEqual(process.stdin.getvalue(), b"reject decision123\n")

    def test_ended_process_cannot_receive_approval(self):
        identifier, process = self.pending_job(approval=True)
        process.poll.return_value = 1
        self.assertEqual(self.request('/api/runs/' + identifier + '/respond',
                                     {"token": "3:decision123", "decision": "approve"})[0], 409)
        self.assertEqual(process.stdin.getvalue(), b"")

    def test_failed_child_cannot_stay_running_from_old_checkpoint(self):
        directory = self.root / "runs/example"
        directory.mkdir()
        (directory / "checkpoint.json").write_text('{"status":"running"}', encoding="utf-8")
        output = self.root / "runs/ui-example.log"
        output.write_text("Run log: " + str(directory), encoding="utf-8")
        process = Mock()
        process.wait.return_value = 1
        web_ui.JOBS["example"] = {"process": process, "output": output, "status": "running"}
        handler = object.__new__(web_ui.Handler)
        handler.watch_job("example")
        self.assertEqual(web_ui.JOBS["example"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
