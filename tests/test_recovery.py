"""Controlled failures: real local Chromium, mocked HTTP, no model API quota."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import socket
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from browser import Browser
from gemini import Gemini, ProviderError
from harness import Agent, RunError, RunLog
from replay import read_run, write_viewer
from state import save_json
from test_agent import WorkspaceCase, Script, call
from tools import Toolbox


def wire(content, usage=5):
    return io.BytesIO(json.dumps({"candidates": [{"finishReason": "STOP", "content": content}],
                                 "usageMetadata": {"totalTokenCount": usage}}).encode())


class ProviderRecoveryTests(WorkspaceCase):
    def test_http_and_timeout_failures_keep_write_and_resume_without_repeating(self):
        failures = [("429", HTTPError("https://example.invalid", 429, "quota", {"Retry-After": "30"}, io.BytesIO(b"test-secret")), "provider_rate_limit"),
                    ("503", HTTPError("https://example.invalid", 503, "unavailable", {}, io.BytesIO(b"unavailable")), "provider_http_error"),
                    ("timeout", TimeoutError("timed out"), "provider_timeout")]
        for label, failure, expected_code in failures:
            with self.subTest(failure=label):
                self.tools = Toolbox(self.workspace)
                filename = label + ".txt"
                provider = Gemini("test-secret")
                with patch("gemini.request.urlopen", side_effect=[wire(call("write_file", path=filename, content="Saved once")), failure]) as request:
                    with self.assertRaises(ProviderError) as raised:
                        self.agent(provider).run("Create and verify a file")
                    self.assertEqual(request.call_count, 2)  # no hidden retry
                self.assertNotIn("test-secret", str(raised.exception))
                state = json.loads((self.log.directory / "checkpoint.json").read_text())
                self.assertEqual(state["failure"]["code"], expected_code)
                self.assertIsNone(state["pending"])
                self.assertEqual(state["requests"], 2)
                self.assertEqual((self.workspace / filename).read_text(), "Saved once")
                if label == "429":
                    self.assertEqual(state["failure"]["retry_after"], "30")
                result = read_run(self.log.directory)["result"]
                self.assertEqual(result["failure"]["code"], expected_code)
                write_viewer(self.log.directory)
                tools = Toolbox(self.workspace)
                with patch("gemini.request.urlopen", side_effect=[wire(call("read_file", path=filename)),
                                                                  wire(call("finish", summary="Recovered", evidence_steps=[2]))]), \
                     patch.object(tools, "write_file") as write:
                    outcome = Agent(provider, tools, self.log, announce=lambda line: None).run(state["task"], resume_state=state)
                write.assert_not_called()
                self.assertEqual(outcome["status"], "succeeded")
                self.assertEqual(outcome["requests"], 4)

    def test_missing_usage_and_partial_model_response_never_execute_actions(self):
        responses = [{"candidates": [{"finishReason": "MAX_TOKENS", "content": call("write_file", path="bad.txt", content="bad")}]},
                     {"candidates": [{"finishReason": "STOP", "content": call("write_file", path="bad.txt", content="bad")}]}]
        for response in responses:
            with self.subTest(response=response), patch("gemini.request.urlopen", return_value=io.BytesIO(json.dumps(response).encode())):
                with self.assertRaises((RunError, ProviderError)):
                    self.agent(Gemini("test")).run("Write a file")
                self.assertFalse((self.workspace / "bad.txt").exists())
                self.assertFalse(any(event["event"] == "tool_call" for event in self.events()))

    def test_request_and_token_budgets_preserve_safe_resume(self):
        provider = Script(call("write_file", path="saved.txt", content="Budget evidence"))
        with self.assertRaisesRegex(RunError, "request limit"):
            self.agent(provider, max_requests=1).run("Create and verify saved.txt")
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.assertEqual(state["failure"]["code"], "request_budget")
        self.assertIsNone(state["pending"])
        provider = Script(call("read_file", path="saved.txt"), call("finish", summary="Verified", evidence_steps=[2]))
        tools = Toolbox(self.workspace)
        with patch.object(tools, "write_file") as write:
            result = Agent(provider, tools, self.log, max_requests=3, announce=lambda line: None).run(state["task"], resume_state=state)
        write.assert_not_called()
        self.assertEqual(result["requests"], 3)
        with self.assertRaises(RunError):
            self.agent(Script(call("write_file", path="over-budget.txt", content="Forbidden")), max_run_tokens=4).run("Budget trial")
        self.assertFalse((self.workspace / "over-budget.txt").exists())
        self.assertEqual(json.loads((self.log.directory / "result.json").read_text())["failure"]["code"], "token_budget")


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Optional Playwright dependency is not installed")
class BrowserRecoveryTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        fixture = Path(__file__).resolve().parents[1] / "browser_demo"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(fixture)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.log = RunLog(self.root / "runs")
        self.browser = Browser(self.log.directory, headless=True, timeout=2000)
        self.addCleanup(lambda: self.browser.close() if self.browser is not None else None)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def agent_for(self, provider, **kwargs):
        return Agent(provider, self.tools, self.log, browser=self.browser, announce=lambda line: None, **kwargs)

    def test_recovers_wrong_role_and_handles_native_and_custom_controls(self):
        first = call("browser_open", url=self.url + "/controls.html")
        first["parts"][0]["thoughtSignature"] = "preserve-me"
        provider = Script(first, call("browser_fill", name="Search topic", text="General"),
                          call("browser_fill", name="Search topic", role="combobox", text="General"),
                          call("browser_click", role="option", name="General tools"),
                          call("browser_select", name="Delivery mode", label="Express"),
                          call("browser_fill", name="Note", text="Recovery works."),
                          call("browser_press", role="textbox", name="Note", key="Enter"),
                          call("browser_verify", text="Selected topic: General tools."),
                          call("browser_verify", text="Delivery mode: Express"),
                          call("browser_verify", text="Saved note: Recovery works."),
                          call("finish", summary="Verified all controls", evidence_steps=[8, 9, 10]))
        result = self.agent_for(provider).run("Use different local controls")
        self.assertEqual(result["status"], "succeeded")
        events = [json.loads(line) for line in self.log.events.read_text().splitlines()]
        failed = next(event["result"] for event in events if event["event"] == "tool_result" and event["step"] == 2)
        self.assertFalse(failed["ok"])
        self.assertIn('combobox "Search topic"', failed["snapshot"])
        self.assertTrue((self.log.directory / failed["screenshot"]).is_file())
        last_request = provider.received[-1]
        snapshots = [part["functionResponse"]["response"] for item in last_request for part in item["parts"]
                     if "functionResponse" in part and "snapshot" in part["functionResponse"]["response"]]
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(last_request[1], first)
        checkpoint = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.assertIn("snapshot", checkpoint["history"][0]["result"])
        self.assertTrue(any(event["event"] == "context_compacted" for event in events))

    def test_unchanged_failed_action_stops_before_third_execution(self):
        provider = Script(call("browser_open", url=self.url + "/controls.html"),
                          call("browser_fill", name="Search topic", text="General"),
                          call("browser_observe"),
                          call("browser_fill", name="Search topic", text="General", reason="Another reason"),
                          call("browser_fill", name="Search topic", role="textbox", text="General"))
        with patch.object(self.browser, "execute", wraps=self.browser.execute) as execute:
            with self.assertRaisesRegex(RunError, "Repeated failed"):
                self.agent_for(provider).run("Trial repeated failure")
        self.assertEqual(len([item for item in execute.call_args_list if item.args[0] == "browser_fill"]), 2)
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.assertIsNone(state["pending"])
        self.assertEqual(state["failure"]["code"], "repeated_browser_failure")
        self.assertTrue(any(event["event"] == "recovery_stop" for event in read_run(self.log.directory)["events"]))

    def test_failed_verification_repetition_is_blocked_even_when_a_clock_changes(self):
        self.browser.page.set_content('<p id="clock">Clock 0</p><h1>Actual result</h1>')
        self.browser.page.set_default_timeout(100)
        provider = Script(call("browser_verify", text="Wrong result"),
                          call("browser_observe"),
                          call("browser_verify", text="Wrong result"),
                          call("browser_verify", text="Wrong result"))
        execute = self.browser.execute
        ticks = [0]
        def changing_clock(name, arguments):
            result = execute(name, arguments)
            if name == "browser_verify":
                ticks[0] += 1
                self.browser.page.locator("#clock").evaluate("(el, tick) => el.textContent='Clock '+tick", ticks[0])
            return result
        with patch.object(self.browser, "execute", side_effect=changing_clock):
            with self.assertRaisesRegex(RunError, "Repeated failed"):
                self.agent_for(provider).run("Verify the result")
        self.assertEqual(ticks[0], 2)

    def test_repeated_invalid_finish_is_not_reset_by_a_new_screenshot(self):
        provider = Script(call("browser_open", url=self.url + "/controls.html"),
                          call("browser_observe"),
                          call("finish", summary="Unverified", evidence_steps=[2]),
                          call("browser_observe"),
                          call("finish", summary="Still unverified", evidence_steps=[4]),
                          call("browser_observe"),
                          call("finish", summary="Another screenshot", evidence_steps=[6]))
        with self.assertRaisesRegex(RunError, "invalid finish"):
            self.agent_for(provider).run("Verify the result")
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.assertEqual(state["failure"]["code"], "repeated_browser_failure")
        self.assertEqual(len([item for item in state["history"] if item["name"] == "finish"]), 2)

    def test_browser_only_excludes_local_tools_and_keeps_handoff(self):
        provider = Script(call("write_file", path="unrelated.txt", content="Do not write"),
                          call("browser_open", url=self.url + "/controls.html"),
                          call("browser_verify", text="Control recovery demo"),
                          call("finish", summary="Page verified", evidence_steps=[3]))
        agent = self.agent_for(provider, browser_only=True)
        names = {item["name"] for item in agent.declarations}
        self.assertNotIn("write_file", names)
        self.assertNotIn("run_command", names)
        self.assertIn("ask_user", names)
        self.assertEqual(agent.run("Only inspect the website")["status"], "succeeded")
        self.assertFalse((self.workspace / "unrelated.txt").exists())

    def test_unavailable_and_missing_pages_return_evidence_without_retry(self):
        result = self.browser.execute("browser_open", {"url": self.url + "/does-not-exist"})
        self.assertFalse(result["ok"])
        self.assertIn("404", result["error"])
        self.assertIn("screenshot", result)
        with socket.socket() as port:
            port.bind(("127.0.0.1", 0))
            missing_url = f"http://127.0.0.1:{port.getsockname()[1]}/"
            # The bound but non-listening socket refuses connections; there is no server.
            result = self.browser.execute("browser_open", {"url": missing_url})
        self.assertFalse(result["ok"])
        self.assertTrue("screenshot" in result or "observation_error" in result)

    def test_image_budget_counts_only_requests_actually_started(self):
        provider = Script(call("browser_open", url=self.url + "/controls.html"), call("browser_observe"), call("browser_observe"))
        agent = self.agent_for(provider, vision=True, max_image_requests=1)
        with self.assertRaisesRegex(RunError, "image-request budget"):
            agent.run("Observe with a bounded image budget")
        self.assertEqual(len(provider.received), 2)
        self.assertEqual(agent.requests, 2)
        self.assertEqual(agent.image_requests, 1)

    def test_failed_observation_is_explicit_when_page_is_closed(self):
        self.browser.page.close()
        result = self.browser.execute("browser_observe", {})
        self.assertFalse(result["ok"])
        self.assertIn("observation_error", result)
        self.assertNotIn("screenshot", result)
        self.assertIn("Fresh observation also failed", result["note"])

    def test_keyboard_submission_can_be_protected_by_approval(self):
        self.assertTrue(self.browser.execute("browser_open", {"url": self.url + "/controls.html"})["ok"])
        self.assertTrue(self.browser.execute("browser_fill", {"name": "Note", "text": "Approval needed"})["ok"])
        policy = {"rules": [{"tool": "browser_press", "match": {"role": "textbox", "name": "Note", "key": "Enter"}}]}
        outcome = self.agent_for(Script(call("browser_press", role="textbox", name="Note", key="Enter")),
                                 approval_policy=policy, detach_on_handoff=True).run("Submit only with approval")
        self.assertEqual(outcome["status"], "waiting_for_approval")
        self.assertEqual(self.browser.page.locator("#saved").inner_text(), "No note saved.")

    def test_expired_session_invalidates_approval_instead_of_submitting(self):
        self.browser.execute("browser_open", {"url": self.url + "/transaction.html"})
        for name, arguments in [("browser_fill", {"name": "Demo username", "text": "Demo User"}),
                                ("browser_click", {"role": "button", "name": "Sign in"}),
                                ("browser_fill", {"name": "Recipient", "text": "Demo Recipient"}),
                                ("browser_fill", {"name": "Demo credits", "text": "7"}),
                                ("browser_click", {"role": "button", "name": "Prepare transaction"})]:
            self.assertTrue(self.browser.execute(name, arguments)["ok"])
        policy = {"rules": [{"tool": "browser_click", "match": {"name": "Confirm mock transaction"}}]}
        self.agent_for(Script(call("browser_click", role="button", name="Confirm mock transaction")),
                       approval_policy=policy, detach_on_handoff=True).run("Confirm only with approval")
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.browser.close()
        self.browser = None
        session_file = self.log.directory / "browser_session.json"
        session = json.loads(session_file.read_text())
        session["storage"]["cookies"] = []  # simulate authentication expiring while detached
        save_json(session_file, session)
        self.browser = Browser(self.log.directory, headless=True, timeout=2000, restore=True)
        result = self.agent_for(Script(call("ask_user", question="Please review the expired login")),
                                approval_policy=policy, detach_on_handoff=True).run(state["task"], resume_state=state,
                                decision=("approve", state["pending"]["approval"]["id"]))
        self.assertEqual(result["status"], "waiting_for_input")
        self.assertEqual(self.browser.page.evaluate("JSON.parse(localStorage.alum_mock_transaction).transactions.length"), 0)
        self.assertTrue(any(event["event"] == "approval_stale" for event in read_run(self.log.directory)["events"]))
