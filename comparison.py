"""Read-only, skill-configured comparison inventory and quote evidence."""

from datetime import date
from decimal import Decimal
import json
import re


def normalized(value):
    return " ".join(value.split())


class Comparison:
    def __init__(self, browser, tools, config):
        self.browser, self.tools, self.config = browser, tools, config
        required = {"input_file", "date_field", "allowed_field", "item_pattern", "group_selector", "title_selector",
                    "items_selector", "count_pattern", "selected_selector", "date_cells_selector",
                    "available_pattern", "unavailable_pattern", "price_pattern", "currency"}
        if not isinstance(config, dict) or required - config.keys():
            raise ValueError("Comparison skill metadata is missing required selector/pattern/input fields")
        source_file = tools.read_file(config["input_file"])
        self.source_hash = source_file["sha256"]
        source = json.loads(source_file["content"].lstrip("\ufeff"))
        self.date = date.fromisoformat(source[config["date_field"]])
        self.allowed = source[config["allowed_field"]]
        if not isinstance(self.allowed, list) or any(not isinstance(item, str) for item in self.allowed):
            raise ValueError("Comparison allowed-items field must be a list of item codes")
        self.item_pattern = re.compile(config["item_pattern"])
        self.state = None

    def groups(self):
        groups = []
        nodes = self.browser.page.locator(self.config["group_selector"])
        for index in range(nodes.count()):
            node = nodes.nth(index)
            heading = node.locator(self.config["title_selector"])
            if heading.count() == 0 or not heading.is_visible():
                continue
            title = normalized(heading.inner_text())
            if not title or any(existing["label"] == title for existing in groups):
                raise ValueError("Comparison groups need unique non-empty observed titles")
            groups.append({"label": title, "node": node})
        return groups

    def inventory(self):
        groups, entries = [], []
        for number, group in enumerate(self.groups(), 1):
            group_id = str(number)
            items = {}
            candidates = group["node"].locator(self.config["items_selector"])
            for index in range(candidates.count()):
                candidate = candidates.nth(index)
                if not candidate.is_visible():
                    continue
                match = self.item_pattern.match(normalized(candidate.inner_text()))
                if not match:
                    continue
                label, item_id = match.group("label"), match.group("id")
                if not self.allowed or item_id in self.allowed:
                    items[item_id] = label
            groups.append({"group_id": group_id, "label": group["label"], "items": items})
            if not items and not self.allowed:
                raise ValueError("A displayed group has no inspectable items; inventory is incomplete")
            entries.extend({"group_id": group_id, "group": group["label"], "item_id": key, "item": label}
                           for key, label in items.items())
        counts = re.findall(self.config["count_pattern"], self.browser.page.locator("body").inner_text())
        if len(counts) != 1 or len(groups) != int(counts[0]) or not entries:
            raise ValueError("Comparison inventory does not cover the displayed group count; load all results before beginning")
        return groups, entries

    def begin(self):
        if self.state is not None:
            raise ValueError("Comparison already started; use comparison_status and complete the existing inventory")
        self.check_date()
        groups, entries = self.inventory()
        self.state = {"url": self.browser.page.url, "date": self.date.isoformat(), "source_hash": self.source_hash,
                      "groups": groups, "entries": entries, "quotes": {}}
        return self.status()

    def check_date(self):
        if "date_control" in self.config:
            self.browser.check_verification({"mode": "input_value", **self.config["date_control"],
                                             "text": self.date.strftime(self.config["input_date_format"])})
        if "result_date_format" in self.config:
            self.browser.check_verification({"mode": "rendered_text", "text": self.date.strftime(self.config["result_date_format"]).lstrip("0")})
        for text in self.config.get("required_text", []):
            self.browser.check_verification({"mode": "rendered_text", "text": text})

    @staticmethod
    def key(group_id, item_id):
        return group_id + ":" + item_id

    def record(self, group_id, item_id):
        if self.state is None or self.browser.page.url != self.state["url"]:
            raise ValueError("Begin comparison on the current results before recording quotes")
        self.check_date()
        if "loading_text" in self.config:
            loading = self.browser.page.get_by_text(self.config["loading_text"], exact=True)
            if any(loading.nth(i).is_visible() for i in range(loading.count())):
                raise ValueError("Price response is still loading; wait and observe before recording a quote")
        entry = next((item for item in self.state["entries"]
                      if item["group_id"] == group_id and item["item_id"] == item_id), None)
        if entry is None:
            raise ValueError("Unknown group/item; use the frozen comparison inventory")
        matches = [item for item in self.groups() if item["label"] == entry["group"]]
        if len(matches) != 1:
            raise ValueError("The comparison group disappeared or changed")
        node = matches[0]["node"]
        selected = node.locator(self.config["selected_selector"])
        if selected.count() != 1:
            raise ValueError("Open the requested item and wait for its selected state before recording")
        match = self.item_pattern.match(normalized(selected.inner_text()))
        if not match or match.group("id") != item_id:
            raise ValueError("Another item is selected; its price cannot be recorded for this item")
        day = self.date.strftime("%d %b").lstrip("0")
        cells = node.locator(self.config["date_cells_selector"])
        values = [normalized(cells.nth(i).inner_text()) for i in range(cells.count()) if cells.nth(i).is_visible()]
        values = [value for value in values if re.search(r"(?<!\d)" + re.escape(day) + r"(?!\w)", value)]
        if len(values) != 1:
            raise ValueError("The requested date has no unique loaded availability; do not use another date or old quote")
        availability = values[0]
        available = re.search(self.config["available_pattern"], availability, re.I)
        unavailable = re.search(self.config["unavailable_pattern"], availability, re.I)
        if available:
            prices = re.findall(self.config["price_pattern"], node.inner_text())
            if len(prices) != 1:
                raise ValueError("The selected available item has no unique displayed price yet")
            price = str(Decimal(prices[0].replace(",", "")))
            outcome = "available"
        elif unavailable:
            price, outcome = None, "unavailable"
        else:
            raise ValueError("Availability is unresolved; inspect the returned message and report a blocker if necessary")
        evidence = self.browser.observe()
        quote = {**entry, "date": self.date.isoformat(), "outcome": outcome, "price": price,
                 "currency": self.config["currency"], "availability": availability,
                 "source_url": self.browser.page.url, "screenshot": evidence["screenshot"]}
        self.state["quotes"][self.key(group_id, item_id)] = quote
        return {**quote, **evidence}

    def status(self):
        if self.state is None:
            raise ValueError("Call comparison_begin first")
        pending = [entry for entry in self.state["entries"]
                   if self.key(entry["group_id"], entry["item_id"]) not in self.state["quotes"]]
        available = [quote for quote in self.state["quotes"].values() if quote["outcome"] == "available"]
        lowest = min((Decimal(quote["price"]) for quote in available), default=None)
        best = [quote for quote in available if Decimal(quote["price"]) == lowest]
        return {"groups": self.state["groups"], "total": len(self.state["entries"]),
                "checked": len(self.state["quotes"]), "pending": pending,
                "complete": not pending, "lowest": best}

    def require_complete(self):
        status = self.status()
        if not status["complete"]:
            raise ValueError(f"Comparison incomplete: {status['checked']} of {status['total']} items checked. "
                             "Continue pending items from comparison_status; one quote is not a complete comparison")
        if self.browser.page.url != self.state["url"]:
            raise ValueError("Comparison source changed; completion cannot use another results page")
        if self.tools.read_file(self.config["input_file"])["sha256"] != self.state["source_hash"]:
            raise ValueError("Comparison input changed after inventory; do not combine different journeys")
        self.check_date()
        groups, entries = self.inventory()
        if groups != self.state["groups"] or entries != self.state["entries"]:
            raise ValueError("Comparison inventory changed; reconcile it before claiming complete coverage")
        if not status["lowest"]:
            raise ValueError("No available priced candidate; report a blocker instead of a cheapest selection")
        return status

    def report(self):
        status = self.require_complete()
        lines = ["# Verified comparison", "", f"Journey date: {self.state['date']}",
                 f"Source: {self.state['url']}", f"Coverage: {status['checked']}/{status['total']} items", "",
                 "| Candidate | Class/item | Outcome | Displayed fare | Availability | Evidence |",
                 "| --- | --- | --- | --- | --- | --- |"]
        for entry in self.state["entries"]:
            quote = self.state["quotes"][self.key(entry["group_id"], entry["item_id"])]
            price = f"{quote['currency']} {quote['price']}" if quote["price"] is not None else "Not available"
            fields = [quote["group"], quote["item"], quote["outcome"], price, quote["availability"], quote["screenshot"]]
            lines.append("| " + " | ".join(value.replace("|", "\\|") for value in fields) + " |")
        lines += ["", "## Lowest eligible displayed fare", ""]
        for quote in status["lowest"]:
            lines.append(f"- {quote['group']} / {quote['item']}: {quote['currency']} {quote['price']}")
        lines += ["", "These are observed displayed ticket/item prices, not guaranteed checkout totals or held availability.",
                  "Equal minima are listed together; apply the requested tie-break using observed journey details."]
        return "\n".join(lines) + "\n"
