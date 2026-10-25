"""Real Chromium integration tests. Install requirements-browser.txt and Chromium first."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import struct
import sys
import threading
import unittest

from browser import Browser
from test_agent import WorkspaceCase, Script, call


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(importlib.util.find_spec("playwright"), "Optional Playwright dependency is not installed")
class BrowserTests(WorkspaceCase):
    def setUp(self):
        super().setUp()
        directory = Path(__file__).resolve().parents[1] / "browser_demo"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(directory)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.browser = Browser(self.root, headless=True, timeout=5000)
        self.addCleanup(self.browser.close)
        self.url = f"http://127.0.0.1:{self.server.server_port}/"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def action(self, tool_name, **arguments):
        return self.browser.execute(tool_name, arguments)

    def test_form_through_agent_loop_with_real_browser_and_screenshots(self):
        confirmation = "Registration confirmed for Demo User (demo@example.com)."
        provider = Script(
            call("browser_open", url=self.url),
            call("browser_fill", name="Full name", text="Demo User"),
            call("browser_fill", name="Email", text="demo@example.com"),
            call("browser_click", role="button", name="Submit registration"),
            call("browser_verify", text=confirmation),
            call("finish", summary="Registration verified", evidence_steps=[5]),
        )
        outcome = self.agent(provider, browser=self.browser).run("Submit the local demo form")
        self.assertEqual(outcome["status"], "succeeded")
        self.assertIn(confirmation, self.browser.page.locator("body").inner_text())
        screenshots = list((self.root / "screenshots").glob("*.png"))
        self.assertEqual(len(screenshots), 5)
        self.assertTrue(all(path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") for path in screenshots))
        self.assertIn('textbox "Full name"', provider.received[1][-1]["parts"][0]["functionResponse"]["response"]["snapshot"])

    def test_failed_actions_and_stale_evidence_cannot_finish(self):
        opened = self.action("browser_open", url=self.url)
        self.assertTrue(opened["ok"], opened)
        self.assertFalse(self.action("browser_verify", text="Not on this page")["ok"])
        evidence = self.action("browser_verify", text="Agent form test")
        self.assertTrue(evidence["ok"])
        self.assertTrue(self.action("browser_fill", name="Full name", text="Changed")["ok"])
        with self.assertRaisesRegex(ValueError, "stale"):
            self.browser.verify_evidence(evidence)
        agent = self.agent(Script(), browser=self.browser)
        agent.observations[1] = {"name": "run_command", "result": {"ok": True, "stdout_truncated": False, "stderr_truncated": False}}
        with self.assertRaisesRegex(ValueError, "browser_verify"):
            agent.verify("Done", [1])
        self.assertFalse(self.action("browser_click", role="button", name="Absent button")["ok"])
        self.assertFalse(self.action("browser_open", url="file:///C:/Windows/win.ini")["ok"])
        self.assertFalse(self.action("browser_scroll", direction="sideways")["ok"])
        self.assertTrue(self.action("browser_scroll", direction="down")["ok"])
        current = self.action("browser_verify", text="Agent form test")
        self.browser.page.get_by_role("heading").evaluate("element => element.remove()")
        with self.assertRaisesRegex(ValueError, "no longer holds"):
            self.browser.verify_evidence(current)

    def test_numeric_spinbutton_fills_and_verifies_without_desktop(self):
        self.browser.page.set_content('<label>Age<input type="number" min="1" max="125" value="40"></label>')
        provider = Script(
            call("browser_fill", role="spinbutton", name="Age", text="21"),
            call("browser_press", role="spinbutton", name="Age", key="Tab"),
            call("browser_verify", mode="input_value", role="spinbutton", name="Age", text="21"),
            call("finish", summary="Numeric age entered and verified", evidence_steps=[3]),
        )
        outcome = self.agent(provider, browser=self.browser).run("Set the numeric passenger age to 21")
        self.assertEqual(outcome["status"], "succeeded")
        self.assertEqual(self.browser.page.get_by_role("spinbutton", name="Age").input_value(), "21")

    def test_unnamed_selects_use_observed_options_and_verify_selected_label(self):
        self.browser.page.set_content('''
            <select id="gender"><option>Gender</option><option value="M">Male</option><option value="F">Female</option></select>
            <select id="nationality"><option>Nationality</option><option selected>India</option></select>
            <select id="berth"><option selected>No Preference</option><option>Lower</option></select>
        ''')
        self.browser.page.set_default_timeout(300)
        provider = Script(
            call("browser_select", name="", label="Male"),
            call("browser_select", name="", containing_option="Gender", label="Male"),
            call("browser_verify", mode="selected_option", name="", containing_option="Gender", text="Male"),
            call("finish", summary="Selected and verified the intended unnamed dropdown", evidence_steps=[3]),
        )
        agent = self.agent(provider, browser=self.browser)
        outcome = agent.run("Choose Male in the Gender dropdown, preserving nationality and berth")
        self.assertEqual(outcome["status"], "succeeded")
        self.assertFalse(agent.observations[1]["result"]["ok"])
        self.assertEqual(self.browser.page.locator("#gender").input_value(), "M")
        self.assertEqual(self.browser.page.locator("#nationality").input_value(), "India")
        self.assertEqual(self.browser.page.locator("#berth").input_value(), "No Preference")
        self.browser.page.locator("#gender").select_option(label="Female")
        with self.assertRaisesRegex(ValueError, "Selected option"):
            self.browser.verify_evidence(agent.observations[3]["result"])
        self.browser.page.locator("#nationality").evaluate("el => el.add(new Option('Gender'))")
        ambiguous = self.action("browser_select", name="", containing_option="Gender", label="Male")
        self.assertFalse(ambiguous["ok"])
        self.assertEqual(self.browser.page.locator("#gender").input_value(), "F")

    def test_visible_text_click_requires_explicit_mode_and_preserves_role(self):
        self.browser.page.set_content('''
            <button aria-label="Shared broken name" onclick="document.querySelector('output').textContent='First'">First</button>
            <button aria-label="Shared broken name" onclick="document.querySelector('output').textContent='Second'">Second</button>
            <a href="#" onclick="document.querySelector('output').textContent='Wrong link'">Second</a>
            <output>Nothing selected</output>
        ''')
        self.browser.page.set_default_timeout(300)
        # The default must not silently change from accessible name to text.
        self.assertFalse(self.action("browser_click", role="button", name="Second")["ok"])
        self.assertEqual(self.browser.page.locator("output").inner_text(), "Nothing selected")
        clicked = self.action("browser_click", role="button", name="Second", match_by="visible_text")
        self.assertTrue(clicked["ok"], clicked)
        self.assertEqual(self.browser.page.locator("output").inner_text(), "Second")

    def test_visible_text_click_is_exact_literal_and_rejects_duplicates(self):
        self.browser.page.set_content('''
            <button onclick="document.querySelector('output').textContent='Exact'">Pick (one)+</button>
            <button onclick="document.querySelector('output').textContent='Wrong'">Pick (one)+ more</button>
            <button>Duplicate</button><button>Duplicate</button><output>Untouched</output>
        ''')
        self.browser.page.set_default_timeout(300)
        self.assertTrue(self.action("browser_click", role="button", name="Pick (one)+", match_by="visible_text")["ok"])
        self.assertEqual(self.browser.page.locator("output").inner_text(), "Exact")
        duplicate = self.action("browser_click", role="button", name="Duplicate", match_by="visible_text")
        self.assertFalse(duplicate["ok"])
        self.assertIn("matched 2 controls", duplicate["error"])
        self.assertFalse(self.action("browser_click", role="button", name=" ", match_by="visible_text")["ok"])
        self.assertFalse(self.action("browser_click", role="button", name="Duplicate", match_by="coordinates")["ok"])

    def test_rendered_option_text_handles_line_breaks_between_child_elements(self):
        self.browser.page.set_content('''
            <div role="listbox"><div role="option" onclick="document.querySelector('output').textContent='Selected'">
              DESTINATION - ZZ <strong>(CITY)</strong><strong style="display:block">REGION</strong>
            </div></div><output>Not selected</output>
        ''')
        option = self.browser.page.get_by_role("option")
        self.assertIn("(CITY)REGION", option.text_content())
        result = self.action("browser_click", role="option", name="DESTINATION - ZZ (CITY) REGION", match_by="visible_text")
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.browser.page.locator("output").inner_text(), "Selected")

    def test_custom_listbox_uses_keyboard_then_exact_accessible_option_name(self):
        self.browser.page.set_content('''
            <input role="listbox" aria-label="STANDARD" readonly
                   style="position:absolute;clip:rect(0,0,0,0);width:1px;height:1px"
                   onkeydown="if(event.code==='Space')document.querySelector('#options').hidden=false">
            <span>STANDARD</span>
            <div role="listbox" id="options" hidden>
              <div role="option" onclick="document.querySelector('input').setAttribute('aria-label','EXPRESS');document.querySelector('#options').hidden=true">EXPRESS</div>
            </div>
        ''')
        opened = self.action("browser_press", role="listbox", name="STANDARD", key="Space")
        self.assertTrue(opened["ok"], opened)
        self.assertIn('option "EXPRESS"', opened["snapshot"])
        chosen = self.action("browser_click", role="option", name="EXPRESS")
        self.assertTrue(chosen["ok"], chosen)
        self.assertEqual(self.browser.page.get_by_role("listbox", name="EXPRESS", exact=True).count(), 1)

    def test_visible_text_click_can_navigate_without_repeating_the_action(self):
        self.browser.page.set_content(f'''
            <form action="{self.url}" method="get">
              <button aria-label="Incorrect label">Open local form</button>
            </form>
        ''')
        result = self.action("browser_click", role="button", name="Open local form", match_by="visible_text")
        self.assertTrue(result["ok"], result)
        self.assertTrue(self.browser.page.url.startswith(self.url))
        self.assertIn("Agent form test", self.browser.page.locator("body").inner_text())


    def test_repeated_cells_are_selected_only_in_the_observed_table_scope(self):
        self.browser.page.set_content('''
            <section><h2>Service Alpha</h2><table><tr>
              <td onclick="document.querySelector('output').textContent='Alpha'">Standard Refresh &#xf01e;</td>
            </tr></table></section>
            <section><h2>Service Beta</h2><table><tr>
              <td onclick="document.querySelector('output').textContent='Beta'">Standard Refresh &#xf01e;</td>
            </tr></table></section><output>Not selected</output>
        ''')
        observation = self.browser.observe()
        scopes = observation["click_scopes"]
        self.assertEqual(len(scopes), 2)
        beta = next(item["scope_id"] for item in scopes if "Service Beta" in item["context"])
        selected = self.action("browser_click", role="cell", name="Standard", match_by="contains_text", scope_id=beta)
        self.assertTrue(selected["ok"], selected)
        self.assertEqual(self.browser.page.locator("output").inner_text(), "Beta")
        self.assertFalse(self.action("browser_click", role="cell", name="Standard", match_by="contains_text")["ok"])
        self.assertFalse(self.action("browser_click", role="cell", name="Standard", match_by="contains_text", scope_id="invented")["ok"])
        self.browser.page.locator(f'[data-wish-click-scope="{beta}"] tr').evaluate("el => el.append(el.firstElementChild.cloneNode(true))")
        duplicate = self.action("browser_click", role="cell", name="Standard", match_by="contains_text", scope_id=beta)
        self.assertFalse(duplicate["ok"])
        self.assertIn("matched 2 controls", duplicate["error"])
        self.browser.page.locator(f'[data-wish-click-scope="{beta}"]').evaluate("el => el.remove()")
        self.assertFalse(self.action("browser_click", role="cell", name="Standard", match_by="contains_text", scope_id=beta)["ok"])

    def test_repeated_tabs_use_the_correct_observed_tablist_scope(self):
        self.browser.page.set_content('''
            <section><h2>Service Alpha</h2><div role="tablist">
              <button role="tab" onclick="document.querySelector('output').textContent='Alpha'">Standard</button>
            </div></section>
            <section><h2>Service Beta</h2><div role="tablist">
              <button role="tab" onclick="document.querySelector('output').textContent='Beta'">Standard</button>
            </div></section><output>Not selected</output>
        ''')
        observation = self.browser.observe()
        beta = next(item for item in observation["click_scopes"] if "Service Beta" in item["context"])
        self.assertEqual(beta["role"], "tablist")
        selected = self.action("browser_click", role="tab", name="Standard", scope_id=beta["scope_id"])
        self.assertTrue(selected["ok"], selected)
        self.assertEqual(self.browser.page.locator("output").inner_text(), "Beta")

    def test_duplicate_buttons_use_exact_text_from_observed_card_context(self):
        self.browser.page.set_content('''
            <section><h2>KOTA DDN AC EXP (12401)</h2>
              <button onclick="document.querySelector('output').textContent='KOTA'">Book Now</button>
            </section>
            <section><h2>HEMKUNT EXPRESS (14610)</h2>
              <button onclick="document.querySelector('output').textContent='HEMKUNT'">Book Now</button>
            </section>
            <output>Not selected</output>
        ''')
        self.assertFalse(self.action("browser_click", role="button", name="Book Now")["ok"])
        self.browser.observe()
        selected = self.action("browser_click", role="button", name="Book Now", scope_text="KOTA DDN AC EXP (12401)")
        self.assertTrue(selected["ok"], selected)
        self.assertEqual(self.browser.page.locator("output").inner_text(), "KOTA")

    def test_scope_text_requires_current_observed_context_and_one_control(self):
        self.browser.page.set_content('''
            <section><h2>Service Alpha</h2>
              <button>Book Now</button><button>Book Now</button>
            </section>
            <section><h2>Service Beta</h2><button>Book Now</button></section>
        ''')
        self.browser.observe()
        unknown = self.action("browser_click", role="button", name="Book Now", scope_text="Service Gamma")
        self.assertFalse(unknown["ok"])
        self.browser.revision += 1
        stale = self.action("browser_click", role="button", name="Book Now", scope_text="Service Beta")
        self.assertFalse(stale["ok"])
        self.assertIn("current browser_observe", stale["error"])
        ambiguous = self.action("browser_click", role="button", name="Book Now", scope_text="Service Alpha")
        self.assertFalse(ambiguous["ok"])
        self.assertIn("matched 0 exact controls", ambiguous["error"])

    def test_unnamed_date_value_and_split_results_text_are_verified_independently(self):
        self.browser.page.set_content('''
            <input id="date" value="25/10/2026" data-committed="25/10/2026"
                   onkeyup="if(event.key!=='Tab')this.dataset.committed=this.value"
                   onblur="this.value=this.dataset.committed">
            <p>DD/MM/YYYY *</p>
            <section aria-label="Search results">
              <span>13 Results for </span><strong>ORIGIN \u2794 DESTINATION | Mon, 26 Oct 2026</strong>
              <span> For Quota | Tatkal</span>
            </section><p hidden>Hidden result</p>
        ''')
        wrong_date = self.action("browser_verify", mode="input_value", role="textbox", name="", text="26/10/2026")
        self.assertFalse(wrong_date["ok"])
        self.assertTrue(self.action("browser_fill", role="textbox", name="", text="26/10/2026")["ok"])
        self.assertTrue(self.action("browser_press", role="textbox", name="", key="Tab")["ok"])
        self.assertFalse(self.action("browser_verify", mode="input_value", role="textbox", name="", text="26/10/2026")["ok"])
        self.assertTrue(self.action("browser_fill", role="textbox", name="", text="26/10/2026")["ok"])
        self.assertTrue(self.action("browser_press", role="textbox", name="", key="ArrowRight")["ok"])
        self.assertTrue(self.action("browser_press", role="textbox", name="", key="Tab")["ok"])
        date = self.action("browser_verify", mode="input_value", role="textbox", name="", text="26/10/2026")
        self.assertTrue(date["ok"], date)
        for fragment in ("26 Oct 2026", "For Quota | Tatkal", "ORIGIN"):
            verified = self.action("browser_verify", mode="rendered_text", text=fragment)
            self.assertTrue(verified["ok"], verified)
        for fragment in ("25 Oct 2026", "Hidden result"):
            self.assertFalse(self.action("browser_verify", mode="rendered_text", text=fragment)["ok"])
        invalid_scope = self.action("browser_verify", mode="rendered_text", role="strong", name="26 Oct 2026", text="26 Oct 2026")
        self.assertFalse(invalid_scope["ok"])
        self.assertIn("omit role and name", invalid_scope["error"])
        self.assertEqual(invalid_scope["error_type"], "ValueError")
        self.browser.page.locator("#date").fill("25/10/2026")
        with self.assertRaisesRegex(ValueError, "does not match"):
            self.browser.verify_evidence(date)


@unittest.skipUnless(sys.platform == "win32" and importlib.util.find_spec("playwright"),
                     "Visible maximized window check requires Windows and Playwright")
class WindowTests(WorkspaceCase):
    def test_visible_browser_is_maximized_with_real_screenshot_dimensions(self):
        directory = self.root / "maximized"
        directory.mkdir()
        visible = Browser(directory, headless=False)
        self.addCleanup(visible.close)
        visible.page.set_content("<h1>Maximized window check</h1>")
        session = visible.context.new_cdp_session(visible.page)
        try:
            window = session.send("Browser.getWindowForTarget")
            self.assertEqual(window["bounds"]["windowState"], "maximized")
        finally:
            session.detach()
        self.assertIsNone(visible.page.viewport_size)
        observation = visible.observe()
        png = (directory / observation["screenshot"]).read_bytes()
        self.assertEqual((observation["image_width"], observation["image_height"]), struct.unpack(">II", png[16:24]))


if __name__ == "__main__":
    unittest.main()
