"""Optional Playwright tools; one isolated browser page per run."""

import hashlib
import json
from pathlib import Path
import struct
from urllib.parse import urlsplit

from tools import STRING, declaration
from state import save_json


MUTATING_TOOLS = {"browser_open", "browser_fill", "browser_click", "browser_scroll", "browser_select", "browser_press"}


DECLARATIONS = [
    declaration("browser_open", "Navigate to an HTTP(S) URL and observe the page.", {"url": STRING}, ["url"]),
    declaration("browser_observe", "Read page roles, names and text; save a viewport screenshot.", {}, []),
    declaration("browser_fill", "Fill an editable textbox, searchbox, combobox or numeric spinbutton by observed exact role/name. role defaults to textbox; native selects use browser_select.",
                {"name": STRING, "text": STRING, "role": STRING}, ["name", "text"]),
    declaration("browser_click", "Click one unique observed control. Default match_by=accessible_name uses its exact accessible name. visible_text matches complete rendered text. Optional scope_id restricts to an observed table/tablist from click_scopes. For a repeated accessible-name control outside those scopes, scope_text may be a distinctive exact text fragment in the latest observation; the control's nearest ancestor must contain it and exactly one matching control. For repeated table cells use scope_id and match_by=contains_text with role=cell. Expanded class tabs use role=tab and an observed tablist scope_id. A hand cursor does not imply role=button. No automatic fallback, invented selector or arbitrary first match.",
                {"role": STRING, "name": STRING, "match_by": STRING, "scope_id": STRING, "scope_text": STRING}, ["role", "name"]),
    declaration("browser_scroll", "Scroll one viewport up or down and observe.", {"direction": STRING}, ["direction"]),
    declaration("browser_select", "Select a native HTML select option by exact accessible name and option label. If multiple selects share an empty name, explicitly set containing_option to a distinctive observed option in the intended select, such as its placeholder. Exactly one select must match; no ordinal guessing. Custom menus use browser_click on observed options.",
                {"name": STRING, "label": STRING, "containing_option": STRING}, ["name", "label"]),
    declaration("browser_press", "Press a navigation/editing key on an observed exact role/name. Supported keys: Enter, Tab, Escape, ArrowDown/Up/Left/Right, Home, End, PageUp, PageDown, Space, Backspace, Delete. Enter/Space may submit or activate a control.",
                {"role": STRING, "name": STRING, "key": STRING}, ["role", "name", "key"]),
    declaration("browser_verify", "Verify browser evidence. Page/results checks use mode=rendered_text with ONLY text and reason; default mode=text checks exact visible text. Neither takes role/name. mode=input_value uses role/name to check a field's exact value. mode=selected_option checks a native select's selected label: provide name (empty for unnamed controls), optional containing_option to distinguish it, and text as the expected selected label. A placeholder option is not the control's accessible name. Successful checks are finish evidence; browser_observe is not.",
                {"text": STRING, "mode": STRING, "role": STRING, "name": STRING, "containing_option": STRING}, ["text"]),
    declaration("browser_extract", "Extract exactly count rendered text items in DOM order from an explicitly observed source_url and role. Use container_role/container_name and heading level to select the requested list. Fails on missing/empty items; never invent or pad. This is per-item verification evidence for finish and write_extracted_file.",
                {"source_url": STRING, "role": STRING, "count": {"type": "integer"},
                 "container_role": STRING, "container_name": STRING, "level": {"type": "integer"},
                 "offset": {"type": "integer"}}, ["source_url", "role", "count"]),
]


EXTRACTION_WRITE = declaration("write_extracted_file", "Write a numbered UTF-8 list directly from a successful browser_extract step, after rechecking every item/source/order. No invented content is accepted. Read the file back and cite matching browser_extract evidence before finish.",
                               {"path": STRING, "extraction_step": {"type": "integer"},
                                "overwrite": {"type": "boolean"}}, ["path", "extraction_step"])


class Browser:
    def __init__(self, directory, headless=False, timeout=10000, restore=False):
        try:
            from playwright.sync_api import sync_playwright, Error
        except ImportError as exc:
            raise ValueError("Browser tools require: python -m pip install -r requirements-browser.txt; then python -m playwright install chromium") from exc
        self.error = Error
        self.session_file = Path(directory).resolve() / "browser_session.json"
        session = None
        if restore:
            if not self.session_file.resolve().is_relative_to(self.session_file.parent):
                raise ValueError("Browser session file leaves the run directory")
            if not self.session_file.is_file():
                raise ValueError("No saved browser session. Use resume --fresh-browser to explicitly start without it")
            session = json.loads(self.session_file.read_text(encoding="utf-8"))
            if session.get("version") != 1 or not isinstance(session.get("storage"), dict):
                raise ValueError("Invalid saved browser session")
            if session["url"] != "about:blank":
                self.validate_url(session["url"])
        self.driver = sync_playwright().start()
        try:
            self.browser = self.driver.chromium.launch(headless=headless, args=[] if headless else ["--start-maximized"])
            viewport = {"viewport": {"width": 1280, "height": 800}} if headless else {"no_viewport": True}
            self.context = self.browser.new_context(**viewport, accept_downloads=False,
                                                    **({"storage_state": session["storage"]} if session else {}))
            self.page = self.context.new_page()
            if not headless:
                window_session = self.context.new_cdp_session(self.page)
                window = window_session.send("Browser.getWindowForTarget")
                window_session.send("Browser.setWindowBounds", {"windowId": window["windowId"], "bounds": {"windowState": "maximized"}})
                window_session.detach()
            self.page.set_default_timeout(timeout)
            self.page.set_default_navigation_timeout(timeout)
            self.directory = Path(directory) / "screenshots"
            self.directory.mkdir(exist_ok=True)
            self.revision = 0
            self.sequence = max((int(p.stem) for p in self.directory.glob("*.png") if p.stem.isdigit()), default=0)
            self.scope_sequence = 0
            self.scope_ids = set()
            self.last_snapshot = None
            self.last_observation_revision = None
            self.restored_observation = None
            if session:
                response = self.page.goto(session["url"], wait_until="domcontentloaded")
                if response is not None and response.status >= 400:
                    raise ValueError(f"Restoring browser page returned HTTP {response.status}")
                self.revision += 1
                self.restored_observation = self.observe()
        except BaseException:
            self.driver.stop()
            raise

    def close(self):
        try:
            self.save_session()
        finally:
            try:
                self.browser.close()
            finally:
                self.driver.stop()

    @staticmethod
    def validate_url(url):
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Use an HTTP(S) URL without embedded credentials")

    @classmethod
    def canonical_url(cls, url):
        cls.validate_url(url)
        parsed = urlsplit(url)
        return parsed._replace(scheme=parsed.scheme.lower(), netloc=parsed.netloc.lower(), path=parsed.path or "/").geturl()

    def save_session(self):
        """Private run data: do not log or export storage contents."""
        save_json(self.session_file, {"version": 1, "url": self.page.url,
                                     "storage": self.context.storage_state(indexed_db=True)})

    def approval_state(self):
        """Conservative binding: any observed content or form-value change needs new approval."""
        state = {"url": self.page.url, "snapshot": self.page.locator("body").aria_snapshot(),
                 "fields": self.page.locator("input, textarea, select").evaluate_all(
                     "els => els.map(e => ({tag:e.tagName,type:e.type,name:e.name,id:e.id,value:e.value,checked:e.checked}))")}
        encoded = json.dumps(state, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return {"url": self.page.url, "sha256": hashlib.sha256(encoded).hexdigest()}

    def observe(self):
        snapshot = self.page.locator("body").aria_snapshot()
        self.last_snapshot = snapshot
        self.last_observation_revision = self.revision
        scopes = []
        containers = self.page.get_by_role("table").or_(self.page.get_by_role("tablist"))
        for index in range(containers.count()):
            table = containers.nth(index)
            if not table.is_visible():
                continue
            role = "tablist" if table.get_attribute("role") == "tablist" else "table"
            identifier = table.get_attribute("data-wish-click-scope")
            if identifier not in self.scope_ids:
                self.scope_sequence += 1
                identifier = f"{role}-{self.scope_sequence}"
                table.evaluate("(el, id) => el.setAttribute('data-wish-click-scope', id)", identifier)
                self.scope_ids.add(identifier)
            context = table.evaluate("""el => {
                let context='';
                for(let p=el.parentElement,n=0;p&&n<5&&!['BODY','HTML'].includes(p.tagName);p=p.parentElement,n++){
                    const range=document.createRange();range.selectNodeContents(p);range.setEndBefore(el);
                    const before=range.toString().replace(/\\s+/g,' ').trim();
                    if(before.length>1600)break;
                    if(before)context=before.slice(-600);
                }
                return context;
            }""")
            table_text = " ".join(table.inner_text().split())
            scopes.append({"scope_id": identifier, "role": role, "context": context,
                           "text": table_text[:1000], "text_truncated": len(table_text) > 1000})
        self.sequence += 1
        path = self.directory / f"{self.sequence:04d}.png"
        screenshot = self.page.screenshot(path=str(path))
        width, height = struct.unpack(">II", screenshot[16:24])
        return {"url": self.page.url, "title": self.page.title(), "snapshot": snapshot[:16000], "click_scopes": scopes,
                "snapshot_truncated": len(snapshot) > 16000,
                "state_fingerprint": self.fingerprint(snapshot),
                "screenshot": f"screenshots/{path.name}", "revision": self.revision,
                "image_width": width, "image_height": height}

    def fingerprint(self, snapshot=None):
        snapshot = self.page.locator("body").aria_snapshot() if snapshot is None else snapshot
        return hashlib.sha256(json.dumps([self.page.url, snapshot], ensure_ascii=True).encode("utf-8")).hexdigest()

    def visible_text(self, text):
        if not text.strip():
            raise ValueError("Verification text cannot be blank")
        self.page.get_by_text(text, exact=True).wait_for(state="visible")

    def native_select(self, name, containing_option=None):
        control = self.page.get_by_role("combobox", name=name, exact=True)
        if containing_option is not None:
            if not containing_option.strip():
                raise ValueError("containing_option must be a distinctive observed non-empty option label")
            control = control.filter(has=self.page.get_by_role("option", name=containing_option,
                                                             exact=True, include_hidden=True))
        return control

    def check_verification(self, selection):
        text = selection["text"]
        if not text.strip():
            raise ValueError("Verification text cannot be blank")
        mode = selection.get("mode", "text")
        if mode not in {"text", "rendered_text", "input_value", "selected_option"}:
            raise ValueError("Verification mode must be text, rendered_text, input_value or selected_option")
        if "containing_option" in selection and mode != "selected_option":
            raise ValueError("containing_option verification requires mode=selected_option")
        if mode == "selected_option":
            if "name" not in selection or selection.get("role", "combobox") != "combobox":
                raise ValueError("selected_option requires name (empty for unnamed selects); its role is combobox")
            control = self.native_select(selection["name"], selection.get("containing_option"))
            control.wait_for(state="visible")
            actual = control.locator("option:checked").evaluate("el => el.label")
            if " ".join(actual.split()) != " ".join(text.split()):
                raise ValueError("Selected option does not match the expected label; correct the dropdown")
            return
        if mode in {"text", "rendered_text"} and ({"role", "name"} & selection.keys()):
            raise ValueError("Page-text verification must omit role and name. Use browser_verify "
                             "with mode=rendered_text and text set to one short expected fragment. "
                             "A 'strong:' text node is not a named control. Use input_value for fields or selected_option for native selects.")
        if mode == "text":
            self.visible_text(text)
            return
        if mode == "input_value" and not {"role", "name"}.issubset(selection):
            raise ValueError("input_value verification requires role and name; use name='' for an unnamed control")
        scope = (self.page.get_by_role(selection["role"], name=selection["name"], exact=True)
                 if mode == "input_value" else self.page.locator("body"))
        scope.wait_for(state="visible")
        if mode == "input_value":
            actual = scope.input_value()
            if actual != text:
                raise ValueError("Input value does not match the expected value; correct the form before continuing")
        elif mode == "rendered_text":
            if " ".join(text.split()) not in " ".join(scope.inner_text().split()):
                raise ValueError("Expected fragment is absent from current rendered text; inspect the date/source instead of inventing a combined heading")

    def verify_evidence(self, result):
        if result["revision"] != self.revision or result["url"] != self.page.url:
            raise ValueError("Browser evidence is stale; verify again after the last action")
        try:
            selection = result["verification"] if "verification" in result else {"text": result["verified_text"]}
            self.check_verification(selection)
        except self.error as exc:
            raise ValueError(f"Browser evidence no longer holds: {exc}") from exc

    def extract_items(self, selection):
        count, offset = selection["count"], selection.get("offset", 0)
        if not 1 <= count <= 100 or not 0 <= offset <= 1000:
            raise ValueError("Extraction count must be 1..100 and offset 0..1000")
        if self.canonical_url(self.page.url) != self.canonical_url(selection["source_url"]):
            raise ValueError("Extraction source URL does not match the current page; do not substitute another search/feed")
        if "container_name" in selection and "container_role" not in selection:
            raise ValueError("container_name requires container_role")
        scope = self.page.locator("body")
        if "container_role" in selection:
            options = {"name": selection["container_name"], "exact": True} if "container_name" in selection else {}
            scope = self.page.get_by_role(selection["container_role"], **options)
        if scope.count() != 1 or not scope.is_visible():
            raise ValueError("Extraction scope must identify exactly one rendered container")
        options = {}
        if "level" in selection:
            if selection["role"] != "heading" or not 1 <= selection["level"] <= 6:
                raise ValueError("level must be 1..6 and requires role=heading")
            options["level"] = selection["level"]
        candidates = scope.get_by_role(selection["role"], **options)
        if candidates.count() > 1000:
            raise ValueError("Extraction matches more than 1000 elements; choose a narrower observed container")
        items, links = [], []
        visible = 0
        for index in range(candidates.count()):
            element = candidates.nth(index)
            if not element.is_visible():
                continue
            visible += 1
            if visible <= offset:
                continue
            text = " ".join(element.inner_text().split())
            if not text:
                raise ValueError("A requested item has no rendered text; refine the observed role/container instead of skipping it")
            items.append(text)
            links.append(element.evaluate("el => {const a=el.matches('a[href]')?el:el.querySelector('a[href]')||el.closest('a[href]'); return a?a.href:null;}"))
            if len(items) == count:
                break
        if len(items) != count:
            raise ValueError(f"Only {len(items)} rendered items are available after offset {offset}; requested {count}. Do not invent missing items or change the source; ask the user or report_blocker.")
        if sum(len(item.encode("utf-8")) for item in items) > 64 * 1024:
            raise ValueError("Extracted text exceeds 64 KiB; narrow the request")
        return {"items": items, "links": links}

    def verify_extraction(self, result):
        if result["revision"] != self.revision or result["url"] != self.page.url:
            raise ValueError("Extraction evidence is stale; extract again after the last browser action")
        try:
            current = self.extract_items(result["selection"])
        except self.error as exc:
            raise ValueError(f"Extraction evidence no longer holds: {exc}") from exc
        if current["items"] != result["items"] or current["links"] != result["links"]:
            raise ValueError("Extracted items, order or links changed; extract again before writing or finishing")

    def execute(self, name, arguments):
        try:
            if name in MUTATING_TOOLS:
                # Even a timed-out action may have changed the page.
                self.revision += 1
            if name == "browser_open":
                url = arguments["url"]
                self.validate_url(url)
                response = self.page.goto(url, wait_until="domcontentloaded")
                if response is not None and response.status >= 400:
                    raise ValueError(f"Page returned HTTP {response.status}")
            elif name == "browser_fill":
                role = arguments.get("role", "textbox")
                if role not in {"textbox", "searchbox", "combobox", "spinbutton"}:
                    raise ValueError("Fill role must be textbox, searchbox, editable combobox or spinbutton; use the observed role")
                self.page.get_by_role(role, name=arguments["name"], exact=True).fill(arguments["text"])
            elif name == "browser_click":
                match_by = arguments.get("match_by", "accessible_name")
                handles = []
                try:
                    scope = self.page
                    if "scope_id" in arguments and "scope_text" in arguments:
                        raise ValueError("Use either the observed scope_id or scope_text, not both")
                    if "scope_id" in arguments:
                        identifier = arguments["scope_id"]
                        if identifier not in self.scope_ids:
                            raise ValueError("Unknown click scope; use a scope_id returned by browser_observe")
                        scope = self.page.locator(f'[data-wish-click-scope="{identifier}"]')
                        if scope.count() != 1 or not scope.is_visible():
                            raise ValueError("Click scope is missing, hidden or duplicated; observe again")
                    if "scope_text" in arguments:
                        if match_by != "accessible_name":
                            raise ValueError("scope_text applies only to exact accessible-name clicks")
                        context = " ".join(arguments["scope_text"].split())
                        observed = " ".join((self.last_snapshot or "").split())
                        if not context or self.last_observation_revision != self.revision - 1 or context not in observed:
                            raise ValueError("scope_text must be a non-empty exact fragment from the current browser_observe result")
                        candidates = self.page.get_by_role(arguments["role"], name=arguments["name"], exact=True).element_handles()
                        matches = []
                        try:
                            for index, element in enumerate(candidates):
                                parent = element.evaluate_handle("el => el.parentElement")
                                try:
                                    while parent.as_element() is not None:
                                        ancestor = parent.as_element()
                                        if ancestor.evaluate("el => el.tagName === 'BODY'"):
                                            break
                                        text = " ".join(ancestor.evaluate("el => el.innerText").split())
                                        if context in text:
                                            count = sum(other.evaluate("(el, parent) => parent.contains(el)", ancestor)
                                                        for other in candidates)
                                            if count == 1:
                                                matches.append(index)
                                            break
                                        next_parent = ancestor.evaluate_handle("el => el.parentElement")
                                        parent.dispose()
                                        parent = next_parent
                                finally:
                                    parent.dispose()
                            if len(matches) != 1:
                                raise ValueError(f"Observed scope_text matched {len(matches)} exact controls; needs exactly one")
                            candidates[matches[0]].click()
                        finally:
                            for element in candidates:
                                element.dispose()
                        target = None
                    else:
                        if match_by == "accessible_name":
                            target = scope.get_by_role(arguments["role"], name=arguments["name"], exact=True)
                        elif match_by in {"visible_text", "contains_text"}:
                            if match_by == "contains_text" and ("scope_id" not in arguments or arguments["role"] != "cell"):
                                raise ValueError("contains_text requires an observed table scope_id and role=cell")
                            text = " ".join(arguments["name"].split())
                            if not text:
                                raise ValueError("Visible click text cannot be blank")
                            handles = scope.get_by_role(arguments["role"]).element_handles()
                            matches = []
                            for element in handles:
                                if not element.is_visible():
                                    continue
                                actual = " ".join(element.inner_text().split())
                                matches_text = text in actual if match_by == "contains_text" else actual == text
                                if matches_text:
                                    matches.append(element)
                            if len(matches) != 1:
                                raise ValueError(f"Visible-text click matched {len(matches)} controls; needs exactly one. "
                                                 "Observe again and prefer the exact accessible name when present. "
                                                 "A control's accessible name or input value is not necessarily its rendered text.")
                            target = matches[0]
                        else:
                            raise ValueError("Click match_by must be accessible_name, visible_text or contains_text")
                        target.click()
                finally:
                    for element in handles:
                        element.dispose()
            elif name == "browser_scroll":
                direction = arguments["direction"]
                if direction not in {"up", "down"}:
                    raise ValueError("direction must be up or down")
                self.page.evaluate("direction => window.scrollBy(0, direction * window.innerHeight)", 1 if direction == "down" else -1)
            elif name == "browser_select":
                self.native_select(arguments["name"], arguments.get("containing_option")).select_option(label=arguments["label"])
            elif name == "browser_press":
                if arguments["key"] not in {"Enter", "Tab", "Escape", "ArrowDown", "ArrowUp", "ArrowLeft", "ArrowRight",
                                            "Home", "End", "PageUp", "PageDown", "Space", "Backspace", "Delete"}:
                    raise ValueError("Unsupported browser key; use a declared navigation/editing key")
                self.page.get_by_role(arguments["role"], name=arguments["name"], exact=True).press(arguments["key"])
            elif name == "browser_verify":
                selection = {key: value for key, value in arguments.items() if key != "reason"}
                self.check_verification(selection)
            elif name == "browser_extract":
                selection = {key: value for key, value in arguments.items() if key != "reason"}
                extracted = self.extract_items(selection)
            elif name != "browser_observe":
                raise ValueError(f"Unknown browser tool: {name}")
            result = {"ok": True, **self.observe()}
            if name == "browser_verify":
                result["verified_text"] = arguments["text"]
                result["verification"] = selection
            if name == "browser_extract":
                result.update(selection=selection, **extracted)
                self.verify_extraction(result)
            self.save_session()
            return result
        except (self.error, ValueError, OSError) as exc:
            result = {"ok": False, "error": str(exc), "error_type": type(exc).__name__,
                      "note": "An action may have taken effect before failing. Inspect this fresh observation, use the exact observed role/name, and change the approach before repeating it."}
            try:
                result.update(self.observe())
            except (self.error, ValueError, OSError) as observation_error:
                result["observation_error"] = str(observation_error)
                result["note"] += " Fresh observation also failed; no screenshot/state is available. Ask for help if the page cannot be observed."
            return result
