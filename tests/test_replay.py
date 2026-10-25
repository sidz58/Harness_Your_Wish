import hashlib
import io
import json
from pathlib import Path
from unittest.mock import Mock, patch

from harness import RunLog
from main import main
from replay import export_run, read_run, write_viewer
from state import exclusive_lock
from test_agent import WorkspaceCase, Script, call


class ReplayTests(WorkspaceCase):
    def test_export_is_portable_and_hashes_match_without_config(self):
        skill = {"name": "fixture", "content": "Verify the result", "sha256": "fixture"}
        self.agent(Script(call("run_command", command="python_version"),
                          call("finish", summary="Checked", evidence_steps=[1])), skill=skill).run("Check runtime")
        (self.log.directory / "config.json").write_text('{"private": "not exported"}')
        image = self.log.directory / "screenshots" / "001.png"
        image.parent.mkdir()
        image.write_bytes(b"test image")
        self.log.record("step_screenshot", step=1, screenshot="screenshots/001.png")
        artifact = self.workspace / "ticket.txt"
        artifact.write_text("Explicit artifact")
        destination = export_run(self.log.directory, self.root / "exports", [artifact])
        self.assertFalse((destination / "config.json").exists())
        self.assertFalse((destination / "checkpoint.json").exists())
        self.assertEqual((destination / "skills/001.md").read_text(), skill["content"])
        self.assertEqual((destination / "artifacts/001-ticket.txt").read_text(), "Explicit artifact")
        self.assertEqual((destination / "screenshots/001.png").read_bytes(), b"test image")
        manifest = json.loads((destination / "manifest.json").read_text())
        for entry in manifest["files"]:
            content = (destination / entry["path"]).read_bytes()
            self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual(entry["bytes"], len(content))
        page = (destination / "replay.html").read_text(encoding="utf-8")
        self.assertNotIn(str(destination), page)
        self.assertIn("No screenshot for tool steps: 2", page)

    def test_logged_html_cannot_escape_embedded_json(self):
        log = RunLog(self.root / "runs")
        payload = '</script><script>window.INJECTED=true</script>'
        log.record("state", task=payload, status="running")
        page = write_viewer(log.directory).read_text(encoding="utf-8")
        self.assertNotIn(payload, page)
        embedded = page.split('<script id="run-data" type="application/json">', 1)[1].split('</script>', 1)[0]
        self.assertEqual(json.loads(embedded)["events"][0]["task"], payload)

    def test_rejects_evidence_path_escape_and_corrupt_log(self):
        for relative in ("../outside.png", "C:/outside.png", "/outside.png", "screenshots\\outside.png"):
            log = RunLog(self.root / "runs")
            log.record("step_screenshot", step=1, screenshot=relative)
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "path"):
                read_run(log.directory)
        log.events.write_text('{"event":', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "line 1"):
            read_run(log.directory)

    def test_missing_images_and_unfinalized_segments_are_reported(self):
        log = RunLog(self.root / "runs")
        log.record("recording_started", video="recordings/segment.mp4")
        log.record("tool_call", step=1, name="browser_open", arguments={})
        log.record("tool_result", step=1, result={"ok": True, "screenshot": "screenshots/missing.png"})
        data = read_run(log.directory)
        self.assertEqual(data["assets"], [])
        self.assertTrue(any("Unfinalized" in warning for warning in data["warnings"]))
        self.assertTrue(any("No screenshot for tool steps: 1" in warning for warning in data["warnings"]))

    def test_cli_refuses_export_while_run_is_locked(self):
        log = RunLog(self.root / "runs")
        log.record("state", status="running")
        with exclusive_lock(log.directory / "run.lock"), patch("main.ROOT", self.root), patch("sys.stderr", new_callable=io.StringIO) as error:
            self.assertEqual(main(["export", log.directory.name]), 1)
        self.assertIn("Another process", error.getvalue())
        self.assertFalse((self.root / "exports").exists())

    def test_handoff_captures_before_and_resume_keeps_events(self):
        recorder = Mock()
        first = self.agent(Script(call("ask_user", question="Filename?")), recorder=recorder, detach_on_handoff=True)
        outcome = first.run("Ask")
        self.assertEqual(outcome["status"], "waiting_for_input")
        recorder.capture.assert_called_once_with(1, "before")
        data = read_run(self.log.directory)
        self.assertTrue(any(e.get("status") == "waiting_for_input" for e in data["events"]))

    def test_capture_failure_after_write_preserves_completed_action(self):
        recorder = Mock()
        recorder.capture.side_effect = [None, OSError("Screen unavailable")]
        with self.assertRaisesRegex(OSError, "Screen unavailable"):
            self.agent(Script(call("write_file", path="saved.txt", content="once")), recorder=recorder).run("Write")
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.assertEqual(state["status"], "failed")
        self.assertIsNone(state["pending"])
        self.assertTrue(state["history"][0]["result"]["ok"])
        self.assertEqual((self.workspace / "saved.txt").read_text(), "once")

    def test_cli_stops_recording_on_handoff_and_returns_failure_on_finalize_error(self):
        for fail in (False, True):
            recorder = Mock()
            if fail:
                recorder.close.side_effect = RuntimeError("Cannot finalize")
            with patch("main.ROOT", self.root), patch("main.Gemini", return_value=Script(call("ask_user", question="Continue?"))), \
                 patch("recording.ScreenRecorder", return_value=recorder), patch("sys.stdout", new_callable=io.StringIO), \
                 patch("sys.stderr", new_callable=io.StringIO):
                code = main(["run", "Ask", "--record-screen", "--detach-on-handoff"])
            self.assertEqual(code, 1 if fail else 0)
            self.assertGreaterEqual(recorder.close.call_count, 1)
            # The computer lock was released even when finalization failed.
            with exclusive_lock(self.root / "runs/computer.lock"):
                pass
