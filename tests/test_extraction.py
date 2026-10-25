"""Source, count, per-item and file-provenance checks with local Chromium only."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from browser import Browser
from harness import Agent, RunError, RunLog
from main import main
from replay import read_run, export_run
from test_agent import WorkspaceCase, Script, call
from tools import Toolbox


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Optional Playwright dependency is not installed")
class ExtractionTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        fixture = Path(__file__).resolve().parents[1] / "browser_demo"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(fixture)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.url = f"http://127.0.0.1:{self.server.server_port}/extraction.html"
        self.log = RunLog(self.root / "runs")
        self.browser = Browser(self.log.directory, headless=True, timeout=3000)
        self.addCleanup(lambda: self.browser.close() if self.browser is not None else None)
        self.selection = {"source_url": self.url, "role": "heading", "level": 3, "container_role": "main", "count": 6}

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_agent(self, provider, source_url=None):
        agent = Agent(provider, self.tools, self.log, browser=self.browser,
                      source_url=source_url, extract_count=6 if source_url else None,
                      announce=lambda line: None)
        return agent, agent.run("Save the first six titles from the requested source")

    def test_report_is_built_from_every_rendered_item_in_dom_order(self):
        provider = Script(call("browser_open", url=self.url), call("browser_extract", **self.selection),
                          call("write_extracted_file", path="report.txt", extraction_step=2),
                          call("read_file", path="report.txt"),
                          call("browser_verify", text="List extraction demo"),
                          call("finish", summary="Heading alone is insufficient", evidence_steps=[4, 5]),
                          call("finish", summary="All extracted titles verified", evidence_steps=[2, 4]))
        agent, outcome = self.run_agent(provider, source_url=self.url)
        self.assertEqual(outcome["status"], "succeeded")
        self.assertEqual((self.workspace / "report.txt").read_text(), "1. Zeta\n2. Alpha\n3. Gamma\n4. Beta\n5. Gamma\n6. Delta\n")
        self.assertEqual(len(agent.extracted_files["report.txt"]["items"]), 6)
        events = read_run(self.log.directory)["events"]
        self.assertTrue(next(e["result"] for e in events if e["event"] == "tool_result" and e["step"] == 1)["snapshot_truncated"])
        failed_finish = next(e["result"] for e in events if e["event"] == "tool_result" and e["step"] == 6)
        self.assertFalse(failed_finish["ok"])
        bundle = export_run(self.log.directory, self.root / "exports", [self.workspace / "report.txt"])
        self.assertIn('"source_url"', (bundle / "events.jsonl").read_text())
        self.assertTrue((bundle / "artifacts/001-report.txt").exists())

    def test_empty_source_cannot_be_replaced_or_saved_as_a_fabricated_list(self):
        source = self.url + "?empty=1"
        selected = {**self.selection, "source_url": source}
        provider = Script(call("browser_open", url=source), call("browser_extract", **selected),
                          call("browser_click", role="button", name="Search something else"),
                          call("browser_extract", **{**selected, "source_url": self.url + "?alternate=1"}),
                          call("write_file", path="report.txt", content="Invented list"),
                          call("report_blocker", message="The requested source has no items; another search requires permission", evidence_steps=[2, 4]))
        _, result = self.run_agent(provider, source_url=source)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse((self.workspace / "report.txt").exists())
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.assertEqual(state["status"], "blocked")
        self.assertIsNone(state["pending"])

    def test_wrong_count_and_skipped_items_are_rejected(self):
        provider = Script(call("browser_open", url=self.url),
                          call("browser_extract", **{**self.selection, "count": 5}),
                          call("browser_extract", **{**self.selection, "offset": 1}),
                          call("report_blocker", message="The requested extraction constraints were not met", evidence_steps=[2, 3]))
        _, result = self.run_agent(provider, source_url=self.url)
        self.assertEqual(result["status"], "blocked")
        errors = [e["result"]["error"] for e in read_run(self.log.directory)["events"]
                  if e["event"] == "tool_result" and not e["result"]["ok"]]
        self.assertIn("exactly 6", errors[0])
        self.assertIn("offset 0", errors[1])

    def test_every_item_is_rechecked_not_only_the_first(self):
        self.assertTrue(self.browser.execute("browser_open", {"url": self.url})["ok"])
        result = self.browser.execute("browser_extract", self.selection)
        self.assertTrue(result["ok"], result)
        self.browser.page.locator("#items h3 a").last.evaluate("el => el.textContent='Changed last item'")
        with self.assertRaisesRegex(ValueError, "items, order or links changed"):
            self.browser.verify_extraction(result)
        agent = Agent(Script(), self.tools, self.log, browser=self.browser, announce=lambda line: None)
        agent.observations[1] = {"name": "browser_extract", "result": result}
        with self.assertRaises(ValueError):
            agent.write_extracted_file("report.txt", 1)
        self.assertFalse((self.workspace / "report.txt").exists())

    def test_missing_item_fails_instead_of_padding(self):
        self.browser.execute("browser_open", {"url": self.url})
        self.browser.page.locator("#items article").last.evaluate("el => el.remove()")
        result = self.browser.execute("browser_extract", self.selection)
        self.assertFalse(result["ok"])
        self.assertIn("Only 5 rendered items", result["error"])
        self.assertIn("screenshot", result)

    def test_existing_unrelated_report_cannot_satisfy_a_refused_write(self):
        (self.workspace / "report.txt").write_text("Old unrelated report")
        provider = Script(call("browser_open", url=self.url), call("browser_extract", **self.selection),
                          call("write_extracted_file", path="report.txt", extraction_step=2),
                          call("read_file", path="report.txt"),
                          call("finish", summary="Cannot certify the old report", evidence_steps=[2, 4]),
                          call("report_blocker", message="Existing report differs; overwrite was not authorized", evidence_steps=[3, 5]))
        _, result = self.run_agent(provider, source_url=self.url)
        self.assertEqual(result["status"], "blocked")
        self.assertEqual((self.workspace / "report.txt").read_text(), "Old unrelated report")
        errors = [e["result"]["error"] for e in read_run(self.log.directory)["events"]
                  if e["event"] == "tool_result" and not e["result"]["ok"]]
        self.assertTrue(any("exact extracted list" in error for error in errors))

    def test_file_provenance_survives_interruption_without_repeating_write(self):
        first = Agent(Script(call("browser_open", url=self.url), call("browser_extract", **self.selection),
                             call("write_extracted_file", path="report.txt", extraction_step=2)),
                      self.tools, self.log, browser=self.browser, source_url=self.url, extract_count=6,
                      announce=lambda line: None)
        original = self.tools.write_file
        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise KeyboardInterrupt()
        with patch.object(self.tools, "write_file", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            first.run("Extract six titles")
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.assertEqual(state["pending"]["name"], "write_extracted_file")
        self.assertIn("report.txt", state["extracted_files"])
        self.browser.close()
        self.browser = None
        self.browser = Browser(self.log.directory, headless=True, restore=True)
        tools = Toolbox(self.workspace)
        provider = Script(call("browser_extract", **self.selection), call("read_file", path="report.txt"),
                          call("finish", summary="Recovered without writing again", evidence_steps=[4, 5]))
        with patch.object(tools, "write_file") as write:
            result = Agent(provider, tools, self.log, browser=self.browser, source_url=self.url, extract_count=6,
                           announce=lambda line: None).run(state["task"], resume_state=state, note="File exists; inspect instead of repeating the write")
        write.assert_not_called()
        self.assertEqual(result["status"], "succeeded")

    def test_cli_snapshots_constraints_and_invalid_options_fail_before_model(self):
        with patch("main.ROOT", self.root), patch("main.Gemini") as model, patch("sys.stderr", new_callable=io.StringIO):
            self.assertEqual(main(["run", "Extract", "--extract-count", "6"]), 1)
            model.assert_not_called()
        with patch("main.ROOT", self.root), patch("main.Gemini") as model, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(main(["on-event", "Extract", "--browser", "--source-url", self.url, "--extract-count", "6",
                                   "--event-file", str(self.root / "trigger.ready")]), 0)
            model.assert_not_called()
        config = json.loads(next((self.root / "jobs").glob("*.json")).read_text())["config"]
        self.assertEqual(config["source_url"], self.url)
        self.assertEqual(config["extract_count"], 6)
