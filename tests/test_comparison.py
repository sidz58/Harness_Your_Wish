"""Complete comparison coverage and price provenance, using local Chromium only."""

import importlib.util
import json
import unittest
from unittest.mock import patch

from browser import Browser
from comparison import Comparison
from harness import Agent, RunLog
from main import load_skill
from test_agent import WorkspaceCase, Script, call
from tools import Toolbox


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Optional Playwright dependency is not installed")
class ComparisonTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        self.log = RunLog(self.root / "runs")
        self.browser = Browser(self.log.directory, headless=True, timeout=1000)
        self.addCleanup(self.browser.close)
        self.config = {**load_skill("irctc-tatkal-search")["metadata"]["comparison"],
                       "group_selector": ".candidate", "title_selector": "h2"}
        self.source = self.workspace / self.config["input_file"]
        self.source.write_text(json.dumps({"journey_date": "2026-10-26", "allowed_classes": []}), encoding="utf-8")
        self.browser.page.set_content('''
          <style>.candidate {display: contents}</style>
          <h1>2 Results for 26 Oct 2026</h1><span>For Quota | Tatkal</span>
          <input aria-label="DD/MM/YYYY *" value="26/10/2026">
          <section class="candidate" id="alpha"><h2>Service Alpha</h2>
            <div role="tablist">
              <button role="tab" aria-selected="true" data-price="100">Basic (A)</button>
              <button role="tab" aria-selected="false" data-price="50">Premium (B)</button>
            </div>
            <table><tr><td>Mon, 26 Oct AVAILABLE-0010</td></tr></table>
            <output>₹ 100</output>
          </section>
          <section class="candidate" id="beta"><h2>Service Beta</h2>
            <div role="tablist">
              <button role="tab" aria-selected="true" data-price="80">Basic (A)</button>
              <button role="tab" aria-selected="false" data-price="70">Premium (B)</button>
            </div>
            <table><tr><td>Mon, 26 Oct AVAILABLE-0010</td></tr></table>
            <output>₹ 80</output>
          </section>
          <script>
            document.querySelectorAll('[role=tab]').forEach(tab => tab.onclick = () => {
              const card = tab.closest('section');
              card.querySelectorAll('[role=tab]').forEach(other => other.setAttribute('aria-selected', 'false'));
              tab.setAttribute('aria-selected', 'true');
              card.querySelector('output').textContent = '₹ ' + tab.dataset.price;
            });
          </script>
        ''')
        self.browser.observe()
        self.scopes = {key: self.browser.page.locator(f"#{key} [role=tablist]").get_attribute("data-wish-click-scope")
                       for key in ("alpha", "beta")}
        self.comparison = Comparison(self.browser, self.tools, self.config)

    def choose(self, group, name="Premium (B)"):
        result = self.browser.execute("browser_click", {"role": "tab", "name": name, "scope_id": self.scopes[group]})
        self.assertTrue(result["ok"], result)

    def complete(self):
        self.comparison.begin()
        self.comparison.record("1", "A")
        self.choose("alpha")
        self.comparison.record("1", "B")
        self.comparison.record("2", "A")
        self.choose("beta")
        self.comparison.record("2", "B")

    def test_one_fare_cannot_finish_and_later_cheaper_class_wins(self):
        status = self.comparison.begin()
        self.assertEqual(status["total"], 4)
        self.comparison.record("1", "A")
        self.assertEqual(len(self.comparison.status()["pending"]), 3)
        with self.assertRaisesRegex(ValueError, "1 of 4"):
            self.comparison.report()
        with self.assertRaisesRegex(ValueError, "Another item is selected"):
            self.comparison.record("1", "B")
        self.choose("alpha")
        self.comparison.record("1", "B")
        self.comparison.record("2", "A")
        self.choose("beta")
        self.comparison.record("2", "B")
        status = self.comparison.require_complete()
        self.assertEqual(status["pending"], [])
        self.assertEqual([(item["group"], item["item_id"], item["price"]) for item in status["lowest"]],
                         [("Service Alpha", "B", "50")])
        self.assertIn("Coverage: 4/4", self.comparison.report())

    def test_unloaded_and_wrong_date_prices_do_not_count(self):
        self.comparison.begin()
        self.browser.page.locator("body").evaluate("el => el.insertAdjacentHTML('beforeend', '<p id=loading>Please Wait...</p>')")
        with self.assertRaisesRegex(ValueError, "still loading"):
            self.comparison.record("1", "A")
        self.browser.page.locator("#loading").evaluate("el => el.remove()")
        cell = self.browser.page.locator("#alpha td")
        for text in ("Mon, 26 Oct Refresh", "Sun, 25 Oct AVAILABLE-0010"):
            cell.evaluate("(el, text) => el.textContent=text", text)
            with self.assertRaises(ValueError):
                self.comparison.record("1", "A")
        self.assertEqual(self.comparison.status()["checked"], 0)
        cell.evaluate("el => el.textContent='Mon, 26 Oct NOT AVAILABLE'")
        quote = self.comparison.record("1", "A")
        self.assertEqual(quote["outcome"], "unavailable")
        self.assertIsNone(quote["price"])
        self.assertEqual(self.comparison.status()["lowest"], [])

    def test_inventory_source_changes_and_ties(self):
        self.browser.page.locator("#beta [data-price='70']").evaluate("el => el.dataset.price='50'")
        self.complete()
        self.assertEqual(len(self.comparison.require_complete()["lowest"]), 2)
        self.source.write_text(json.dumps({"journey_date": "2026-10-26", "allowed_classes": ["A"]}))
        with self.assertRaisesRegex(ValueError, "input changed"):
            self.comparison.require_complete()

    def test_missing_groups_and_changed_inventory_are_rejected(self):
        self.browser.page.locator("h1").evaluate("el => el.textContent='3 Results for 26 Oct 2026'")
        with self.assertRaisesRegex(ValueError, "displayed group count"):
            self.comparison.begin()
        self.browser.page.locator("h1").evaluate("el => el.textContent='2 Results for 26 Oct 2026'")
        self.complete()
        self.browser.page.locator("#beta [role=tab]").last.evaluate("el => el.remove()")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            self.comparison.require_complete()

    def test_agent_rejects_premature_finish_then_writes_computed_minimum(self):
        provider = Script(
            call("comparison_begin"),
            call("comparison_record", group_id="1", item_id="A"),
            call("write_comparison_report", path="report.md"),
            call("browser_verify", mode="rendered_text", text="26 Oct 2026"),
            call("finish", summary="First fare is cheapest", evidence_steps=[4]),
            call("browser_click", role="tab", name="Premium (B)", scope_id=self.scopes["alpha"]),
            call("comparison_record", group_id="1", item_id="B"),
            call("comparison_record", group_id="2", item_id="A"),
            call("browser_click", role="tab", name="Premium (B)", scope_id=self.scopes["beta"]),
            call("comparison_record", group_id="2", item_id="B"),
            call("write_comparison_report", path="report.md"),
            call("read_file", path="report.md"),
            call("browser_verify", mode="rendered_text", text="26 Oct 2026"),
            call("finish", summary="Incorrect model summary: first fare 100 is cheapest", evidence_steps=[12, 13]),
        )
        agent = Agent(provider, self.tools, self.log, browser=self.browser, announce=lambda line: None,
                      skill={"name": "comparison-test", "content": "Compare all items", "metadata": {"comparison": self.config}})
        result = agent.run("Compare every item and choose the lowest fare")
        self.assertEqual(result["status"], "succeeded")
        self.assertFalse(agent.observations[3]["result"]["ok"])
        self.assertFalse(agent.observations[5]["result"]["ok"])
        self.assertIn("INR 50", result["summary"])
        self.assertNotIn("first fare 100", result["summary"])
        saved = (self.workspace / "report.md").read_text(encoding="utf-8")
        self.assertIn("Service Beta", saved)
        self.assertIn("Coverage: 4/4", saved)
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        self.assertEqual(len(state["comparison"]["quotes"]), 4)
        agent._perform("comparison_record", {"group_id": "2", "item_id": "B", "reason": "Refresh a quote"})
        self.assertIsNone(agent.comparison_report, "A changed ledger requires regenerating the report")

    def test_resume_retains_quotes_and_pending_coverage(self):
        skill = {"name": "comparison-test", "content": "Compare all items", "metadata": {"comparison": self.config}}
        provider = Script(call("comparison_begin"), call("comparison_record", group_id="1", item_id="A"),
                          call("ask_user", question="Continue the comparison?"))
        first = Agent(provider, self.tools, self.log, browser=self.browser, skill=skill,
                      detach_on_handoff=True, announce=lambda line: None)
        self.assertEqual(first.run("Compare all fares")["status"], "waiting_for_input")
        state = json.loads((self.log.directory / "checkpoint.json").read_text())
        resumed = Agent(Script(call("comparison_status"),
                               call("report_blocker", message="Three items are still pending", evidence_steps=[4])),
                        Toolbox(self.workspace), self.log, browser=self.browser, skill=skill, announce=lambda line: None)
        result = resumed.run("Compare all fares", resume_state=state, answer="Continue")
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(resumed.observations[4]["result"]["checked"], 1)
        self.assertEqual(len(resumed.observations[4]["result"]["pending"]), 3)


class ComparisonSkillTests(WorkspaceCase):
    def test_malformed_metadata_cannot_silently_disable_coverage(self):
        skills = self.root / "skills"
        skills.mkdir()
        for metadata in ("", "[]", "{broken}"):
            with self.subTest(metadata=metadata), patch("main.ROOT", self.root):
                (skills / "broken.md").write_text(f"---\nmetadata: {metadata}\n---\nCompare all fares", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "JSON object on one line"):
                    load_skill("broken")

    def test_windows_skill_metadata_remains_enforced(self):
        content = load_skill("irctc-tatkal-search")["content"]
        skills = self.root / "skills"
        skills.mkdir()
        (skills / "windows.md").write_bytes(content.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))
        with patch("main.ROOT", self.root):
            config = load_skill("windows")["metadata"]["comparison"]
        self.assertEqual(config["group_selector"], "app-train-avl-enq")


if __name__ == "__main__":
    unittest.main()
