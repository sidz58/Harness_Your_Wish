from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import threading
from unittest.mock import Mock, patch
import unittest

from approval import action_digest, validate_decision, validate_policy
from browser import Browser
from harness import Agent, RunLog
from main import main
from replay import export_run, read_run
from state import save_json
from test_agent import WorkspaceCase, Script, call


POLICY = {"rules": [{"tool": "browser_click", "match": {"role": "button", "name": "Confirm mock transaction"}}]}
RECEIPT = "Confirmed mock transaction: 7 demo credits to Demo Recipient."


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class PolicyTests(WorkspaceCase):
    def test_invalid_policies_fail_explicitly(self):
        for policy in ({}, {"rules": []}, {"rules": [{"tool": [], "match": {}}]},
                       {"rules": [{"tool": "browser_click", "match": {"reason": "please"}}]},
                       {"rules": [{"tool": "unknown", "match": {}}]}):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                validate_policy(policy)

    def test_approval_id_and_exact_arguments_are_bound(self):
        arguments = {"role": "button", "name": "Confirm", "reason": "Submit"}
        pending = {"name": "browser_click", "arguments": arguments.copy(),
                   "approval": {"id": "correct", "status": "pending", "action_sha256": action_digest("browser_click", arguments)}}
        with self.assertRaisesRegex(ValueError, "exact pending action"):
            validate_decision(pending, ("approve", "different"))
        pending["arguments"]["name"] = "Another action"
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            validate_decision(pending, ("approve", "correct"))


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Optional Playwright dependency is not installed")
class ApprovalBrowserTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        fixture = Path(__file__).resolve().parents[1] / "browser_demo"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(fixture)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}/transaction.html"
        self.policy_file = self.root / "policy.json"
        save_json(self.policy_file, POLICY)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def prepare(self):
        return Script(call("browser_open", url=self.url),
                      call("browser_fill", name="Demo username", text="Demo User"),
                      call("browser_click", role="button", name="Sign in"),
                      call("browser_fill", name="Recipient", text="Demo Recipient"),
                      call("browser_fill", name="Demo credits", text="7"),
                      call("browser_click", role="button", name="Prepare transaction"),
                      call("browser_click", role="button", name="Confirm mock transaction"))

    def cli(self, argv, provider):
        with patch("main.ROOT", self.root), patch("main.Gemini", return_value=provider), \
             patch("sys.stdout", new_callable=io.StringIO) as output, patch("sys.stderr", new_callable=io.StringIO) as error:
            code = main(argv)
        return code, output.getvalue(), error.getvalue()

    def pause(self, vision=False):
        code, output, error = self.cli(["run", "Prepare mock transaction", "--browser", "--headless",
                                        "--approval-policy", str(self.policy_file), "--detach-on-handoff",
                                        "--min-request-interval", "0"] + (["--vision"] if vision else []), self.prepare())
        self.assertEqual(code, 0, error)
        directory = next(path for path in (self.root / "runs").iterdir() if path.is_dir())
        state = json.loads((directory / "checkpoint.json").read_text())
        self.assertEqual(state["status"], "waiting_for_approval")
        self.assertIn("Approve: python main.py resume", output)
        session = json.loads((directory / "browser_session.json").read_text())
        origin = session["storage"]["origins"][0]
        local = {entry["name"]: entry["value"] for entry in origin["localStorage"]}
        self.assertEqual(json.loads(local["alum_mock_transaction"])["transactions"], [])
        self.assertTrue(session["storage"]["cookies"])
        return directory, state

    def restore(self, directory):
        browser = Browser(directory, headless=True, restore=True)
        self.addCleanup(browser.close)
        return browser

    def test_detached_approval_restores_login_executes_once_and_exports_no_session(self):
        directory, state = self.pause(vision=True)
        identifier = state["pending"]["approval"]["id"]
        # Configuration is snapshotted: later changes to the source policy cannot weaken it.
        self.policy_file.write_text("{}")
        provider = Script(call("browser_verify", text=RECEIPT),
                          call("browser_verify", text="Confirmed transactions: 1."),
                          call("finish", summary="Confirmed once", evidence_steps=[9]))
        code, output, error = self.cli(["resume", directory.name, "--approve", identifier], provider)
        self.assertEqual(code, 0, error)
        self.assertIn("Confirmed once", output)
        self.assertTrue(any("inlineData" in part for item in provider.received[0] for part in item["parts"]))
        browser = self.restore(directory)
        self.assertIn("Signed in as Demo User.", browser.page.locator("body").inner_text())
        self.assertIn(RECEIPT, browser.page.locator("body").inner_text())
        self.assertEqual(browser.page.evaluate("JSON.parse(localStorage.alum_mock_transaction).transactions.length"), 1)
        data = read_run(directory)
        self.assertEqual(len([event for event in data["events"] if event["event"] == "approval_consumed"]), 1)
        self.assertEqual(len([event for event in data["events"] if event["event"] == "browser_restored"]), 1)
        destination = export_run(directory, self.root / "exports")
        self.assertFalse((destination / "browser_session.json").exists())
        self.assertIn("approval_decision", (destination / "replay.html").read_text(encoding="utf-8"))

    def test_rejection_cancels_without_model_or_browser_and_cannot_resume(self):
        directory, state = self.pause()
        identifier = state["pending"]["approval"]["id"]
        with patch("main.ROOT", self.root), patch("browser.Browser") as browser, patch("main.Gemini") as model, \
             patch("sys.stdout", new_callable=io.StringIO) as output_stream:
            code = main(["resume", directory.name, "--reject", identifier])
            browser.assert_not_called()
            model.assert_not_called()
        self.assertEqual(code, 0)
        self.assertIn("not executed", output_stream.getvalue())
        self.assertEqual(json.loads((directory / "checkpoint.json").read_text())["status"], "cancelled")
        restored = self.restore(directory)
        self.assertEqual(restored.page.evaluate("JSON.parse(localStorage.alum_mock_transaction).transactions.length"), 0)
        code, _, error = self.cli(["resume", directory.name, "--approve", identifier], Script())
        self.assertEqual(code, 1)
        self.assertIn("cancelled", error)

    def test_wrong_id_and_changed_page_cannot_execute(self):
        directory, state = self.pause()
        code, _, error = self.cli(["resume", directory.name, "--approve", "wrong"], Script())
        self.assertEqual(code, 1)
        self.assertIn("exact pending action", error)
        session_path = directory / "browser_session.json"
        session = json.loads(session_path.read_text())
        for item in session["storage"]["origins"][0]["localStorage"]:
            if item["name"] == "alum_mock_transaction":
                value = json.loads(item["value"])
                value["draft"]["amount"] = "99"
                item["value"] = json.dumps(value)
        save_json(session_path, session)
        # After the stale decision, this scripted provider only asks a question; it cannot submit.
        code, output, error = self.cli(["resume", directory.name, "--approve", state["pending"]["approval"]["id"]],
                                       Script(call("ask_user", question="Review changed transaction?")))
        self.assertEqual(code, 0, error)
        self.assertIn("NOT executed", output)
        self.assertEqual(self.restore(directory).page.evaluate("JSON.parse(localStorage.alum_mock_transaction).transactions.length"), 0)

    def test_inline_approval_also_passes_through_gate(self):
        log = RunLog(self.root / "runs")
        browser = Browser(log.directory, headless=True)
        self.addCleanup(browser.close)
        provider = self.prepare()
        # Continue the scripted provider after the protected call.
        calls = list(provider.contents) + [call("browser_verify", text=RECEIPT), call("finish", summary="Inline confirmed", evidence_steps=[8])]
        def approve(question):
            identifier = agent.pending["approval"]["id"]
            return "approve " + identifier
        recorder = Mock()
        agent = Agent(Script(*calls), self.tools, log, browser=browser, approval_policy=POLICY, recorder=recorder,
                      ask=approve, announce=lambda line: None)
        self.assertEqual(agent.run("Mock inline approval")["status"], "succeeded")
        self.assertEqual(browser.page.evaluate("JSON.parse(localStorage.alum_mock_transaction).transactions.length"), 1)
        phases = [item.args for item in recorder.capture.call_args_list]
        self.assertEqual(phases.count((7, "before")), 1)
        self.assertIn((7, "approved"), phases)

    def test_visible_text_click_still_pauses_before_protected_action(self):
        log = RunLog(self.root / "runs")
        browser = Browser(log.directory, headless=True)
        self.addCleanup(browser.close)
        calls = list(self.prepare().contents)
        calls[-1] = call("browser_click", role="button", name="Confirm mock transaction", match_by="visible_text")
        agent = Agent(Script(*calls), self.tools, log, browser=browser, approval_policy=POLICY,
                      detach_on_handoff=True, announce=lambda line: None)
        self.assertEqual(agent.run("Mock visible text approval")["status"], "waiting_for_approval")
        self.assertEqual(agent.pending["arguments"]["match_by"], "visible_text")
        self.assertEqual(browser.page.evaluate("JSON.parse(localStorage.alum_mock_transaction).transactions.length"), 0)

    def test_scoped_click_preserves_approval_and_scope_during_handoff(self):
        log = RunLog(self.root / "runs")
        browser = Browser(log.directory, headless=True)
        self.addCleanup(browser.close)
        browser.page.set_content('''<h2>Scoped action</h2><table><tr><td>
          <button onclick="document.querySelector('output').textContent='Confirmed once'">Confirm mock transaction</button>
        </td></tr></table><output>Pending</output>''')
        scope = browser.observe()["click_scopes"][0]["scope_id"]
        def approve(_question):
            self.assertEqual(browser.page.locator("output").inner_text(), "Pending")
            return "approve " + agent.pending["approval"]["id"]
        agent = Agent(Script(call("browser_click", role="button", name="Confirm mock transaction", scope_id=scope),
                             call("browser_verify", text="Confirmed once"),
                             call("finish", summary="Confirmed once", evidence_steps=[2])),
                      self.tools, log, browser=browser, approval_policy=POLICY, ask=approve, announce=lambda _: None)
        self.assertEqual(agent.run("Mock scoped approval")["status"], "succeeded")

    def test_approval_cannot_replay_an_interrupted_submission(self):
        directory, state = self.pause()
        identifier = state["pending"]["approval"]["id"]
        original = Browser.execute
        def interrupt_after_click(browser, name, arguments):
            result = original(browser, name, arguments)
            if name == "browser_click" and arguments["name"] == "Confirm mock transaction":
                raise KeyboardInterrupt()
            return result
        with patch.object(Browser, "execute", interrupt_after_click):
            code, _, _ = self.cli(["resume", directory.name, "--approve", identifier], Script())
        self.assertEqual(code, 130)
        state = json.loads((directory / "checkpoint.json").read_text())
        self.assertEqual(state["pending"]["approval"]["status"], "consumed")
        code, _, error = self.cli(["resume", directory.name, "--approve", identifier], Script())
        self.assertEqual(code, 1)
        self.assertIn("No pending approval", error)
        provider = Script(call("browser_verify", text="Confirmed transactions: 1."),
                          call("finish", summary="Inspected interrupted confirmation", evidence_steps=[8]))
        code, _, error = self.cli(["resume", directory.name, "--note", "Submission may have completed; inspect without repeating"], provider)
        self.assertEqual(code, 0, error)
        self.assertEqual(self.restore(directory).page.evaluate("JSON.parse(localStorage.alum_mock_transaction).transactions.length"), 1)

    def test_direct_protected_call_cannot_bypass_gate(self):
        directory, state = self.pause()
        browser = self.restore(directory)
        agent = Agent(Script(), self.tools, RunLog.reopen(directory), browser=browser,
                      approval_policy=POLICY, detach_on_handoff=True, announce=lambda line: None)
        arguments = {"role": "button", "name": "Confirm mock transaction", "reason": "Attempt direct call"}
        agent.pending = {"step": 1, "name": "browser_click", "arguments": arguments}
        from harness import ApprovalPending
        with self.assertRaises(ApprovalPending):
            agent.perform("browser_click", arguments)
        self.assertEqual(browser.page.evaluate("JSON.parse(localStorage.alum_mock_transaction).transactions.length"), 0)

    def test_missing_session_fails_and_fresh_browser_is_explicit(self):
        log = RunLog(self.root / "runs")
        with self.assertRaisesRegex(ValueError, "fresh-browser"):
            Browser(log.directory, headless=True, restore=True)
        browser = Browser(log.directory, headless=True)
        self.addCleanup(browser.close)
        self.assertIsNone(browser.restored_observation)
        self.assertEqual(browser.page.url, "about:blank")
