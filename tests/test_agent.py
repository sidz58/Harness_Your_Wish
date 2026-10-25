import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from gemini import Gemini, ProviderError
from harness import Agent, RunError, RunLog
from main import ScriptedDemo, main
from tools import MAX_FILE_BYTES, MAX_OUTPUT_BYTES, Toolbox, validate_call


def call(tool_name, **args):
    return {"role": "model", "parts": [{"functionCall": {
        "name": tool_name, "args": {"reason": "Test action", **args},
    }}]}


class Script:
    name, model = "test", "test-model"

    def __init__(self, *contents):
        self.contents = iter(contents)
        self.received = []
        self.instructions = []

    def generate(self, contents, declarations, instruction):
        self.received.append(copy.deepcopy(contents))
        self.instructions.append(instruction)
        return next(self.contents), {"totalTokenCount": 5}


class WorkspaceCase(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.tools = Toolbox(self.workspace)

    def execute(self, name, **args):
        return self.tools.execute(name, {"reason": "Test", **args})

    def agent(self, provider, **kwargs):
        self.log = RunLog(self.root / "logs")
        return Agent(provider, self.tools, self.log, announce=lambda line: None, **kwargs)

    def events(self):
        return [json.loads(line) for line in self.log.events.read_text(encoding="utf-8").splitlines()]


class ToolTests(WorkspaceCase):
    def test_file_roundtrip_and_explicit_overwrite(self):
        self.assertTrue(self.execute("write_file", path="notes.txt", content="नमस्ते\n")['ok'])
        self.assertEqual(self.execute("read_file", path="notes.txt")["content"], "नमस्ते\n")
        self.assertFalse(self.execute("write_file", path="notes.txt", content="changed")["ok"])
        self.assertTrue(self.execute("write_file", path="notes.txt", content="changed", overwrite=True)["ok"])
        self.assertEqual(self.execute("read_file", path="notes.txt")["content"], "changed")
        self.assertEqual([e['name'] for e in self.execute("list_files", path=".")["entries"]], ["notes.txt"])

    def test_paths_cannot_escape_workspace(self):
        outside = self.root / "outside.txt"
        outside.write_text("must remain unchanged", encoding="utf-8")
        for path in ("../outside.txt", str(outside), "notes.txt:secret", "C:outside.txt"):
            with self.subTest(path=path):
                self.assertFalse(self.execute("read_file", path=path)["ok"])
                self.assertFalse(self.execute("write_file", path=path, content="bad", overwrite=True)["ok"])
        self.assertEqual(outside.read_text(), "must remain unchanged")

    def test_symlink_escape(self):
        outside = self.root / "outside.txt"
        outside.write_text("private")
        try:
            (self.workspace / "link.txt").symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"Host does not permit symlinks: {exc}")
        self.assertFalse(self.execute("read_file", path="link.txt")["ok"])
        self.assertFalse(self.execute("write_file", path="link.txt", content="bad", overwrite=True)["ok"])

    def test_errors_do_not_return_partial_file_content(self):
        (self.workspace / "large.txt").write_bytes(b"a" * (MAX_FILE_BYTES + 1))
        (self.workspace / "binary.txt").write_bytes(b"\xff")
        for path in ("large.txt", "binary.txt", "missing.txt"):
            result = self.execute("read_file", path=path)
            self.assertFalse(result["ok"])
            self.assertNotIn("content", result)

    def test_argument_validation(self):
        for name, args in (("delete_file", {}), ("read_file", {"path": "a"}),
                           ("read_file", {"path": "a", "reason": "test", "extra": True}),
                           ("write_file", {"path": "a", "content": "b", "reason": "test", "overwrite": "yes"}),
                           ("finish", {"summary": "done", "reason": "test", "evidence_steps": [True]})):
            with self.subTest(name=name, args=args), self.assertRaises(ValueError):
                validate_call(name, args)

    def test_command_allowlist_exit_status_and_output_limit(self):
        self.assertFalse(self.execute("run_command", command="python_version; whoami")["ok"])
        self.tools = Toolbox(self.workspace, commands={
            "fail": [sys.executable, "-c", "import sys; print('failure'); sys.exit(7)"],
            "large": [sys.executable, "-c", f"print('x' * {MAX_OUTPUT_BYTES + 10})"],
        })
        failed = self.execute("run_command", command="fail")
        self.assertFalse(failed["ok"])
        self.assertEqual(failed["returncode"], 7)
        large = self.execute("run_command", command="large")
        self.assertTrue(large["stdout_truncated"])
        self.assertEqual(len(large["stdout"]), MAX_OUTPUT_BYTES)

    def test_command_timeout_is_reported(self):
        self.tools = Toolbox(self.workspace, commands={
            "sleep": [sys.executable, "-c", "import time; time.sleep(10)"],
        }, command_timeout=0.1)
        result = self.execute("run_command", command="sleep")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "TimeoutExpired")


class LoopTests(WorkspaceCase):
    def test_cli_default_and_explicit_fractional_pacing_are_saved(self):
        for options in ([], ["--min-request-interval", "0.5"]):
            with self.subTest(options=options):
                provider = Script(call("run_command", command="python_version"),
                                  call("finish", summary="Checked", evidence_steps=[1]))
                with patch("main.ROOT", self.root), patch("main.Gemini", return_value=provider), \
                        patch("sys.stdout", new_callable=io.StringIO):
                    self.assertEqual(main(["run", "Check runtime", "--workspace", str(self.workspace), *options]), 0)
                saved = sorted((self.root / "runs").glob("*/config.json"), key=lambda p: p.stat().st_mtime)[-1]
                self.assertEqual(json.loads(saved.read_text())["min_request_interval"], 0.5)

    def test_request_pacing_uses_elapsed_time_and_logs_wait(self):
        now = [0.0]
        starts = []
        class TimedScript(Script):
            def generate(inner, *args):
                starts.append(now[0])
                now[0] += 2
                return super().generate(*args)
        provider = TimedScript(call("run_command", command="python_version"),
                               call("finish", summary="Checked", evidence_steps=[1]))
        def sleep(seconds):
            now[0] += seconds
        with patch("harness.time.monotonic", side_effect=lambda: now[0]), patch("harness.time.sleep", side_effect=sleep):
            self.agent(provider, min_request_interval=5).run("Check runtime")
        self.assertEqual(starts, [0.0, 5.0])
        waits = [e for e in self.events() if e["event"] == "request_pacing"]
        self.assertEqual(waits[0]["seconds"], 3)

    def test_full_offline_demo_runs_real_tools_and_verifies_output(self):
        (self.workspace / "notes.txt").write_text("Example notes\n", encoding="utf-8")
        outcome = self.agent(ScriptedDemo()).run("Write and verify a report")
        self.assertEqual(outcome["status"], "succeeded")
        self.assertIn("Example notes", (self.workspace / "report.md").read_text())
        self.assertIn("Python", (self.workspace / "report.md").read_text())
        self.assertEqual(outcome["verified_files"], ["report.md"])
        self.assertEqual(json.loads((self.log.directory / "result.json").read_text())["status"], "succeeded")

    def test_finish_rejects_write_only_evidence_then_allows_readback(self):
        provider = Script(call("write_file", path="out.txt", content="answer"),
                          call("finish", summary="premature", evidence_steps=[1]),
                          call("read_file", path="out.txt"),
                          call("finish", summary="verified", evidence_steps=[3]))
        outcome = self.agent(provider).run("Create out.txt")
        self.assertEqual(outcome["summary"], "verified")
        results = [e["result"] for e in self.events() if e["event"] == "tool_result"]
        self.assertFalse(results[1]["ok"])

    def test_finish_rejects_stale_and_missing_evidence(self):
        provider = Script(call("write_file", path="out.txt", content="old"),
                          call("read_file", path="out.txt"),
                          call("write_file", path="out.txt", content="new", overwrite=True),
                          call("finish", summary="stale", evidence_steps=[2]))
        with self.assertRaises(RunError):
            self.agent(provider, max_requests=4).run("Update a file")
        results = [e["result"] for e in self.events() if e["event"] == "tool_result"]
        self.assertIn("stale", results[-1]["error"])
        self.assertEqual(self.events()[-1]["status"], "failed")

    def test_no_text_only_success(self):
        with self.assertRaisesRegex(RunError, "no tool call"):
            self.agent(Script({"role": "model", "parts": [{"text": "Done!"}]})).run("Do something")

    def test_rejected_tool_error_is_visible_to_model(self):
        provider = Script(call("read_file", path="missing.txt"), call("run_command", command="python_version"),
                          call("finish", summary="Runtime checked", evidence_steps=[2]))
        self.agent(provider).run("Check runtime")
        result = provider.received[1][-1]["parts"][0]["functionResponse"]["response"]
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "FileNotFoundError")

    def test_user_handoff_and_resume(self):
        provider = Script(call("ask_user", question="Which runtime?"),
                          call("run_command", command="python_version"),
                          call("finish", summary="Runtime checked", evidence_steps=[2]))
        self.agent(provider, ask=lambda prompt: "Python").run("Check my runtime")
        states = [e["status"] for e in self.events() if e["event"] == "state"]
        self.assertEqual(states, ["running", "waiting_for_input", "running", "succeeded"])

    def test_step_budget_applies_to_all_calls_in_a_batch(self):
        batch = call("write_file", path="first.txt", content="first")
        batch["parts"] += call("write_file", path="second.txt", content="second")["parts"]
        with self.assertRaisesRegex(RunError, "step limit"):
            self.agent(Script(batch), max_steps=1).run("Write files")
        self.assertTrue((self.workspace / "first.txt").exists())
        self.assertFalse((self.workspace / "second.txt").exists())

    def test_token_budget_stops_actions_after_oversized_response(self):
        with self.assertRaisesRegex(RunError, "token budget"):
            self.agent(Script(call("write_file", path="out.txt", content="bad")), max_run_tokens=4).run("Task")
        self.assertFalse((self.workspace / "out.txt").exists())

    def test_default_unlimited_tokens_still_records_large_usage(self):
        class LargeUsage(Script):
            def generate(inner, *args):
                content, _ = super().generate(*args)
                return content, {"totalTokenCount": 50000}
        provider = LargeUsage(call("run_command", command="python_version"),
                              call("finish", summary="Checked", evidence_steps=[1]))
        outcome = self.agent(provider).run("Check runtime")
        self.assertEqual(outcome["status"], "succeeded")
        self.assertEqual(outcome["tokens"], 100000)
        self.assertEqual(self.events()[-1]["status"], "succeeded")

    def test_provider_error_is_not_retried_or_hidden(self):
        class Unavailable(Script):
            def generate(self, *args):
                raise ProviderError("HTTP 429: quota exhausted")
        with self.assertRaises(ProviderError):
            self.agent(Unavailable()).run("Task")
        self.assertEqual(len([e for e in self.events() if e["event"] == "model_request"]), 1)
        self.assertEqual(self.events()[-1]["status"], "failed")


class SkillTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.skills = self.root / "skills"
        self.skills.mkdir()

    def test_custom_skill_reaches_every_request_and_is_logged(self):
        content = "# Custom procedure\nCheck the Python runtime and verify its output.\n"
        data = content.encode("utf-8")
        (self.skills / "custom.md").write_bytes(data)
        provider = Script(call("run_command", command="python_version"),
                          call("finish", summary="Runtime checked", evidence_steps=[1]))
        with patch("main.ROOT", self.root), patch("main.Gemini", return_value=provider), patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["run", "Check runtime", "--skill", "custom"]), 0)
        self.assertEqual(len(provider.instructions), 2)
        for instruction in provider.instructions:
            self.assertIn(content, instruction)
        events_file = next((self.root / "runs").glob("*/events.jsonl"))
        events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines()]
        loaded = [event for event in events if event["event"] == "skill_loaded"]
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["content"], content)
        self.assertEqual(loaded[0]["sha256"], hashlib.sha256(data).hexdigest())

    def test_invalid_skills_fail_before_provider_creation(self):
        for name, data in (("empty", b" \n"), ("binary", b"\xff"),
                           ("large", b"a" * (MAX_FILE_BYTES + 1))):
            (self.skills / f"{name}.md").write_bytes(data)
        for name in ("missing", "empty", "binary", "large", "../outside", "custom.md"):
            with self.subTest(name=name), patch("main.ROOT", self.root), patch("main.Gemini") as provider, patch("sys.stderr", new_callable=io.StringIO) as stderr:
                self.assertEqual(main(["run", "Task", "--skill", name]), 1)
                self.assertIn("ERROR:", stderr.getvalue())
                provider.assert_not_called()

    def test_list_skills_needs_no_credentials(self):
        (self.skills / "custom.md").write_text("Procedure", encoding="utf-8")
        with patch("main.ROOT", self.root), patch.dict("os.environ", {}, clear=True), patch("main.Gemini") as provider, patch("sys.stdout", new_callable=io.StringIO) as stdout:
            self.assertEqual(main(["skills"]), 0)
            self.assertEqual(stdout.getvalue().strip(), "custom")
            provider.assert_not_called()


class ProviderTests(unittest.TestCase):
    def test_gemini_wire_format_preserves_signatures_and_call_ids(self):
        content = call("run_command", command="python_version")
        content["parts"][0]["thoughtSignature"] = "opaque-signature"
        content["parts"][0]["functionCall"]["id"] = "call-1"
        response = {"candidates": [{"finishReason": "STOP", "content": content}],
                    "usageMetadata": {"totalTokenCount": 10}}
        with patch("gemini.request.urlopen", side_effect=lambda *a, **kw: io.BytesIO(json.dumps(response).encode())) as mocked:
            provider = Gemini("test-secret")
            returned, usage = provider.generate([{"role": "user", "parts": [{"text": "test"}]}], [], "instruction")
            self.assertEqual(returned, content)
            self.assertEqual(usage["totalTokenCount"], 10)
            req = mocked.call_args.args[0]
            payload = json.loads(req.data)
            self.assertEqual(req.get_header("X-goog-api-key"), "test-secret")
            self.assertNotIn("test-secret", req.full_url)
            self.assertEqual(payload["toolConfig"]["functionCallingConfig"]["mode"], "ANY")

    def test_incomplete_response_is_not_executable(self):
        data = {"candidates": [{"finishReason": "MAX_TOKENS", "content": call("write_file", path="a", content="b")}]}
        with patch("gemini.request.urlopen", return_value=io.BytesIO(json.dumps(data).encode())):
            with self.assertRaisesRegex(ProviderError, "incomplete"):
                Gemini("test").generate([], [], "instruction")

    def test_http_errors_redact_key_and_do_not_retry(self):
        exc = HTTPError("https://example.invalid", 429, "quota", {"Retry-After": "30"}, io.BytesIO(b"test-secret"))
        with patch("gemini.request.urlopen", side_effect=exc) as mocked:
            with self.assertRaises(ProviderError) as caught:
                Gemini("test-secret").generate([], [], "instruction")
        self.assertNotIn("test-secret", str(caught.exception))
        self.assertIn("429", str(caught.exception))
        self.assertIn("30", str(caught.exception))
        self.assertEqual(mocked.call_count, 1)

    def test_missing_key_fails_before_network(self):
        with patch.dict("os.environ", {}, clear=True), patch("gemini.request.urlopen") as mocked, patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["run", "Check files"]), 1)
            mocked.assert_not_called()


if __name__ == "__main__":
    unittest.main()
