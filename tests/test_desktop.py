"""Unit tests never move the pointer. Real editor test requires RUN_DESKTOP_TESTS=1."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from desktop import Desktop, DesktopStopped, DECLARATIONS
from harness import Agent, RunError, RunLog
from test_agent import WorkspaceCase, Script, call
from tools import validate_call


class DesktopTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.desktop = Desktop.__new__(Desktop)
        self.desktop.gui = Mock()
        self.desktop.gui.FailSafeException = type("FailSafeException", (Exception,), {})
        self.desktop.gui.size.return_value = (3200, 1800)
        self.desktop.gui.KEYBOARD_KEYS = ["ctrl", "s", "f12"]
        self.desktop.stop_file = self.root / "STOP"
        self.desktop.stopped = threading.Event()
        self.desktop.foreground = Mock(return_value=123)
        self.desktop.revision = 0
        self.desktop.last = {"observation_id": 1, "revision": 0, "captured_at": time.monotonic(),
                             "foreground": 123, "image_width": 1600, "image_height": 900,
                             "screen_width": 3200, "screen_height": 1800}
        self.desktop.observe = Mock(return_value={"observation_id": 2})

    def test_scaled_coordinates_and_stale_focus_rejection(self):
        result = self.desktop.execute("desktop_click", {"observation_id": 1, "x": 500, "y": 200, "button": "left", "clicks": 1})
        self.assertTrue(result["ok"], result)
        self.desktop.gui.click.assert_called_once_with(1000, 400, clicks=1, button="left", interval=0.1)
        self.assertFalse(self.desktop.execute("desktop_keys", {"observation_id": 1, "keys": ["ctrl", "s"]})["ok"])

    def test_focus_age_bounds_and_keys_fail_before_input(self):
        self.desktop.foreground.return_value = 456
        self.assertFalse(self.desktop.execute("desktop_keys", {"observation_id": 1, "keys": ["ctrl", "s"]})["ok"])
        self.desktop.gui.hotkey.assert_not_called()
        self.desktop.last = {"observation_id": 3, "captured_at": time.monotonic() - 61}
        with self.assertRaisesRegex(ValueError, "older"):
            self.desktop.require_observation(3)
        with self.assertRaises(ValueError):
            validate_call("desktop_click", {"reason": "test", "observation_id": 1, "x": True, "y": 0, "button": "left", "clicks": 1}, DECLARATIONS)
        validate_call("desktop_keys", {"reason": "test", "observation_id": 1, "keys": ["ctrl", "s"]}, DECLARATIONS)

    def test_emergency_stop_is_fatal(self):
        self.desktop.stop_file.touch()
        with self.assertRaises(DesktopStopped):
            self.desktop.execute("desktop_observe", {})
        self.desktop.observe.assert_not_called()

    def test_stop_interrupts_api_pacing(self):
        agent = self.agent(Script(), desktop=self.desktop, min_request_interval=5)
        agent.last_request_started = time.monotonic()
        self.desktop.stopped.set()
        with self.assertRaises(DesktopStopped), patch("harness.time.sleep") as sleep:
            agent.pace_request()
        sleep.assert_not_called()

    def test_desktop_batch_is_rejected_before_actions(self):
        batch = call("desktop_observe")
        batch["parts"] += call("desktop_observe")["parts"]
        with self.assertRaisesRegex(RunError, "exactly one"):
            self.agent(Script(batch), desktop=self.desktop).run("Observe")
        self.desktop.observe.assert_not_called()

    def test_desktop_completion_requires_current_visual_evidence(self):
        self.desktop.revision = 1
        agent = self.agent(Script(), desktop=self.desktop)
        agent.observations[1] = {"name": "run_command", "result": {"ok": True, "stdout_truncated": False, "stderr_truncated": False}}
        with self.assertRaisesRegex(ValueError, "desktop_verify"):
            agent.verify("done", [1])
        with self.assertRaisesRegex(ValueError, "stale"):
            self.desktop.verify_evidence({"observation_id": 1, "revision": 0})


@unittest.skipUnless(os.environ.get("RUN_DESKTOP_TESTS") == "1", "Real desktop test is opt-in")
class DesktopIntegration(WorkspaceCase):
    def test_real_editor_saves_unicode_through_agent_loop(self):
        log = RunLog(self.root / "logs")
        ready = self.root / "ready.json"
        output = self.workspace / "note.txt"
        fixture = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--fixture", str(ready), str(output)])
        self.addCleanup(lambda: fixture.wait(timeout=5) if fixture.poll() is not None else self.stop_fixture(fixture))
        deadline = time.monotonic() + 15
        while not ready.exists():
            if fixture.poll() is not None or time.monotonic() > deadline:
                self.fail("Temporary editor did not become ready")
            time.sleep(0.1)
        location = json.loads(ready.read_text())
        desktop = Desktop(log.directory)
        self.addCleanup(desktop.close)
        text = "Desktop tools work. नमस्ते!"

        class EditorScript(Script):
            def generate(inner, contents, declarations, instruction):
                results = [p["functionResponse"]["response"] for item in contents for p in item["parts"] if "functionResponse" in p]
                if any(not result["ok"] for result in results):
                    raise AssertionError(results[-1])
                stage = len(results)
                observed = results[-1] if results else {}
                if stage == 0:
                    next_call = call("desktop_observe")
                elif stage == 1:
                    x = round(location["x"] * observed["image_width"] / observed["screen_width"])
                    y = round(location["y"] * observed["image_height"] / observed["screen_height"])
                    next_call = call("desktop_click", observation_id=observed["observation_id"], x=x, y=y, button="left", clicks=1)
                elif stage == 2:
                    next_call = call("desktop_type", observation_id=observed["observation_id"], text=text)
                elif stage == 3:
                    next_call = call("desktop_keys", observation_id=observed["observation_id"], keys=["ctrl", "s"])
                elif stage == 4:
                    next_call = call("read_file", path="note.txt")
                elif stage == 5:
                    next_call = call("desktop_observe")
                elif stage == 6:
                    next_call = call("desktop_verify", observation_id=observed["observation_id"], finding="Scripted test: saved editor; file checked separately")
                else:
                    next_call = call("finish", summary="Saved and read back Unicode note", evidence_steps=[5, 7])
                inner.received.append(contents)
                return next_call, {"totalTokenCount": 1}

        outcome = Agent(EditorScript(), self.tools, log, desktop=desktop, announce=lambda line: None).run("Save a note in the test editor")
        self.assertEqual(outcome["status"], "succeeded")
        self.assertEqual(output.read_text(encoding="utf-8"), text)
        self.assertGreater(len(list((log.directory / "desktop").glob("*.png"))), 3)

    @staticmethod
    def stop_fixture(process):
        process.terminate()
        process.wait(timeout=5)


def editor_fixture(ready, output):
    import tkinter as tk
    root = tk.Tk()
    root.title("Alum Track temporary test editor")
    root.geometry("700x400+100+100")
    root.attributes("-topmost", True)
    tk.Label(root, text="Temporary test editor — Ctrl+S saves the test file").pack()
    editor = tk.Text(root, font=("Consolas", 16))
    editor.pack(fill="both", expand=True)
    status = tk.Label(root, text="Not saved")
    status.pack()
    def save(event=None):
        Path(output).write_text(editor.get("1.0", "end-1c"), encoding="utf-8")
        status.config(text="Saved")
        return "break"
    root.bind("<Control-s>", save)
    def publish():
        root.lift()
        editor.focus_force()
        Path(ready).write_text(json.dumps({"x": editor.winfo_rootx() + 60, "y": editor.winfo_rooty() + 40}))
    root.after(500, publish)
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--fixture":
        editor_fixture(sys.argv[2], sys.argv[3])
    else:
        unittest.main()
