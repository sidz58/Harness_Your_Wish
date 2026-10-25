# Reliability assessment

## Clickable Refresh cells and repeated train containers

In run `20261024T232910Z-26c57be9` the agent passed results verification but could
not load prices. The initial class tiles have semantic role=cell even though
hovering shows a hand cursor. Guessing a button or joining train title/class into
one control name cannot locate them. The generic tool also needed a way to
restrict repeated class labels to the intended train's table.

Observations now return click_scopes for visible tables/tablists, with stable
in-process IDs, nearby identifying text and explicitly truncated text previews.
browser_click can use the observed scope_id; contains_text is an explicit mode
limited to scoped cells and requires exactly one visible match. Other matching
modes retain exact/complete semantics. Expanded tabs use their observed tablist
scope. No automatic fallback, arbitrary first match, coordinate click or hidden
availability endpoint was added. Normal approval interception still occurs
before a scoped browser_click, and scope IDs survive the approval observation.

A public IRCTC UI check clicked the intended class tile and obtained displayed
date-specific availability and a fare; a saved screenshot confirms it. No account
credentials, login, passenger data, Book Now or payment were used. Local tests
cover selecting the second of repeated tables/tabs, duplicate/missing targets,
unknown scope rejection and payment approval before a scoped click. Full
model-driven comparison across every train/class remains a separate live check.

## Wrong default date and false completion loop

Run `20261024T230114Z-296ae7fd` searched the old date after a failed fill targeting
the date-format caption instead of the unnamed textbox. The model then guessed
a combined summary string containing a result count and arrow, repeatedly cited
failed assertions or plain observations as completion evidence, and claimed
comparison without valid proof. Reports from that run are not valid evidence for
the requested journey date, regardless of whether a file was written.

The shared verification tool now supports mode=input_value with an observed
role/name (including name="" for an unnamed textbox), and mode=rendered_text for
literal fragments across child nodes. Both are rechecked at completion; default
exact-text checks and legacy verified_text records retain their original meaning.
Skills check the configured date before search and separately check the requested
date on results, without copying an old result count, arrow or wrong date.

A public-form check exposed a second issue: a filled date reverted on blur.
Filling the required value, pressing ArrowRight and then Tab committed it and
passed input_value verification on the actual site. This check did not log in,
submit a search, book or pay. A local widget regression reproduces the reversion
and tests that commit sequence, wrong-date rejection and split-text verification.

Repeated failed assertions and invalid finish calls are now tracked independently
of changing clock text. Plain observation is not verification; successful
corrective browser actions/new valid verification permit recovery. Tests cover
the changing-clock and changing-evidence-ID loops. Unlimited request/step/image/
token budgets remain available; this failure guard is separate from those budgets.
The full local regression suite passed, with the opt-in real-desktop test skipped;
the updated widget regression passed after its final refinement. This does not
prove the model will follow every instruction or establish a qualifying booking.

## Station option and custom dropdown targeting

The user's next search rehearsal (`20261024T225223Z-dd7521a0`) repeated a
visible-text station-option click, guessed several roles for the quota control,
and attempted an unconfigured shell/pyautogui click. The latter was rejected by
the command allowlist and is not an available browser recovery mechanism.

Inspection found two different causes:

- The option had a correct accessible name. Its raw DOM text joined city and
  region without whitespace, while rendered inner_text used a line break. The
  initial visible-text matcher filtered raw textContent and therefore missed
  the full label. Explicit visible-text matching now uses normalized rendered
  text, retaining role restriction, uniqueness, and approval interception.
- The quota was a custom widget with a keyboard-accessible listbox input whose
  accessible name was its value. It was not a native select, a GENERAL button,
  or an input containing GENERAL as rendered text. Exact-role browser_press
  with Space opened its options; an accessible-name option click selected the
  requested quota. No automatic widget-type fallback was added.

A public-page check successfully selected the observed destination via its exact
accessible name and changed GENERAL to TATKAL through this keyboard/option path.
No credentials, login, Search Trains, booking or payment were used. Skills now
prefer that observed path, inspect asynchronously committed values instead of
clicking a selected/disappeared option again, and reject arbitrary shell clicks.
Local regression checks cover split-element text, custom keyboard listboxes,
literal/unique visible-text matching and existing payment approval interception.
This does not establish full authenticated-search or booking reliability.

## IRCTC welcome dialog: visible label differs from accessible name

Live search rehearsal `20261024T221811Z-181cff6e` (2026-10-25 India time)
failed before login or searching. The task was:

> Read irctc_journey.local.json. Search the exact configured journey under Tatkal,
> using the named credentials only if login is required. Compare observed eligible
> fares and save the configured search report. Do not press Book Now, submit Aadhaar
> verification, book or pay. Ask me if a login challenge requires my help. Report
> incomplete coverage or unsupported controls honestly.

The saved screenshot displayed two language buttons. The DOM exposed distinct
visible text but the same malformed accessible name for both. An exact accessible
name of English did not exist. The model repeated that call instead of changing
its approach; the repeated-action guard stopped a third execution. No search
result, credential or personal input is copied into this documentation.

The shared browser_click tool now has explicit match_by=visible_text. It matches
the complete text within the requested role, treats text literally, and requires
a unique control. Default accessible-name targeting never silently falls back.
Approvals still intercept the same browser_click action before execution. A name
such as Pay & Book continues to match its policy in either targeting mode; a
different live label still requires a corresponding policy. Generic instructions
and the IRCTC skills explain when to select this mode. This does not make repeated
train-card labels unique or establish end-to-end IRCTC booking reliability.

Local Chromium tests passed for explicit mode selection, role restriction,
exact/literal matching, duplicate rejection, existing form behavior and approval
interception before execution. The existing rejection/stale/consumed approval
tests also passed. No model requests or live booking/payment were made in these
tests. A new live search rehearsal is needed to validate the next website step.
A separate language-only landing-page check encountered
net::ERR_HTTP2_PROTOCOL_ERROR before reaching the dialog. It did not use account
data or perform login, search, booking or payment, and provides no live success
evidence for the fix. No network workaround or hidden retry was introduced.

This milestone tests safe failure and explicit recovery of the general harness.
It does not establish a success rate across arbitrary websites. The implementation
does not select a provider automatically or retry a submission automatically.

## Evidence from the user's flight run

Sources: [events](runs/20261024T105623Z-0e3c6c31/events.jsonl) and
[result](runs/20261024T105623Z-0e3c6c31/result.json), run on 2026-10-24.

- Steps 1–7 checked the runtime and read/listed unrelated workspace files before
  opening the website. General tool-selection guidance was insufficient here.
  The new optional `--browser-only` mode removes file/terminal tools for web tasks.
- The saved page exposed a combobox named "Where to?". Steps 9 and 13 requested a
  textbox with that name; the original fill tool supported only textboxes. The
  generic fill tool now accepts an explicitly observed editable role. Native
  selects and keyboard navigation are separate tools, with no automatic locator
  substitution and no website-specific selectors in the adapter.
- Historical full browser snapshots accumulated in request context. Only the
  latest full snapshot is now retained there; logs/checkpoints retain originals.
- The run stopped after request 16 with 90,891 reported tokens against its 80,000
  local ceiling. Its returned actions were not executed. This was the harness's
  observed token limit, not evidence of a provider quota error. Raising the ceiling
  alone would not correct the role mismatch or irrelevant actions.

The live flight search has not been rerun by this assessment, and no fares from
that unsuccessful search are treated as verified results for the requested date.

## Challenge: YouTube scope drift and insufficient extraction evidence

The user's prompt was:

> Open youtube.com, and save the titles of the first 6 videos to a text file labelled youtube_report.txt in my workspace

It was run with:

```bash
python main.py run "Open youtube.com, and save the titles of the first 6 videos to a text file labelled youtube_report.txt in my workspace" --browser --max-requests 30 --max-run-tokens 300000
```

Sources: saved [task/config](runs/20261024T115106Z-67fa04d5/config.json),
[step log](runs/20261024T115106Z-67fa04d5/events.jsonl), and
[result](runs/20261024T115106Z-67fa04d5/result.json). The result reported success
after 21 requests and 129,284 reported tokens. This incident was observed by the
user with a live model; the new behavior below is verified with local scripted tests.

### What happened

- The initial homepage observation at step 2 showed "Try searching to get started"
  and "Start watching videos to help us build a feed of videos you'll love."
  No homepage video list was available in that isolated browser session. This is
  evidence about that session, not a claim about every YouTube homepage.
- The agent chose "trending", tried other feeds, and then searched for "python
  tutorial" at step 12. The user had not authorized that replacement topic/source.
- Step 15 contained a truncated search-results snapshot. Five saved titles were
  present in its text; the sixth saved title, "Python for Beginners - Full Course",
  was absent from every browser observation before the write. We cannot treat that
  item as supported by the evidence the model received. Vision was disabled.
- Steps 16 and 17 wrote/read the file successfully. Step 18 tried to finish without
  browser verification. Step 19 attempted to verify the document title as visible
  text and timed out. Step 20 verified just the first video title.
- The harness then accepted `finish` citing file readback and that single visible
  title. Those checks proved a file existed and one title was visible; they did
  not establish the requested source, all six items or their order.

### Why this was a challenge

The agent treated absence of requested content as permission to choose another
task. A successful file write was mistaken for task completion, and coarse browser
verification could not detect an unsupported item. The existing failed-action
guard also did not detect this drift because many wrong actions returned success.
Increasing the token budget did not address any of those correctness problems.

### General response implemented

- Guidance preserves the user's source, query, filters and order. Missing content
  should trigger a question or `report_blocker`, never a silently chosen substitute.
- `browser_extract` reads a bounded exact count of rendered text items directly
  from a supplied source URL and role/container. It preserves DOM order and
  duplicates, ignores non-rendered elements, and fails on missing or empty items.
  It can read targeted items even when the general page snapshot was truncated.
- `write_extracted_file` constructs the numbered file from a successful extraction
  record, without accepting invented content from the model. Before writing and
  before accepting completion, the selected items and links are rechecked. A
  matching extraction plus file readback is required; a page heading alone cannot
  verify this kind of report. Provenance survives a process interruption.
  If an existing destination prevents writing, unrelated old contents cannot
  satisfy completion and are left unchanged unless overwrite is authorized.
- Optional `--source-url URL --extract-count N` supplies an operator-enforced
  contract. It locks the exact source URL, requires the count and first matching
  items (offset zero), and removes freeform writes/commands. It does not disable
  all navigation, but a changed source cannot supply an accepted extraction/report.
- `report_blocker` records an evidence-backed `blocked` outcome, separately from
  `succeeded`. Existing output files are not silently deleted or overwritten.

There are no YouTube URLs, video selectors or special cases in the extraction
implementation. Task-specific URL/role/count choices are data supplied to the
general tools. The live retry below validates empty-feed blocker handling;
successful extraction from a populated live website remains unvalidated.

### Live retry result

Run `20261024T122246Z-dea8d929` used this prompt:

> Open https://www.youtube.com/ and save the first 6 homepage video titles to youtube_report_checked.txt. If the feed is unavailable, report_blocker with evidence without choosing another search.

Flags: `--browser --source-url https://www.youtube.com/ --extract-count 6
--max-requests 20 --max-run-tokens 300000`.

The saved observation showed **"Try searching to get started"** and no homepage
video list. The agent opened the homepage, observed it, then called
`report_blocker` citing steps 1 and 2. It made no alternate search and created no
`workspace/youtube_report_checked.txt`. The final status was `blocked`, with
3 requests and 7,713 reported tokens. These counts describe this run only.

Evidence: [events](runs/20261024T122246Z-dea8d929/events.jsonl) and
[result](runs/20261024T122246Z-dea8d929/result.json). This validates reporting an
unavailable feed; it does not validate successful live list extraction.

The remaining semantic boundary is explicit: a model must choose the correct
role/container and understand the requested task. DOM order can differ from visual
grid order, and the same URL can display different filters/state. The URL/count
contract enforces its declared constraints, not every natural-language condition.
Without that contract, freeform file tools remain available for general tasks;
prompt guidance alone is not a hard source restriction.

## Controlled verification

Tests use scripted model replies, mocked model HTTP responses and real Chromium
against loopback fixtures. They consume no model API quota. A simulated expired
login removes the mock application's cookie; it does not certify any real site's
authentication model. Scenarios and assertions live in the linked test files.

| Scenario | Checked behavior | Evidence |
| --- | --- | --- |
| HTTP 429, HTTP 503, request timeout after a completed write | Failure is explicit, counters/state survive, there is no hidden retry, and manual resume reads/verifies without writing again. Retry-After is preserved when supplied. | [test_recovery.py](tests/test_recovery.py) |
| Partial model response or missing token usage | Proposed actions are not executed; failure is retained. | [test_recovery.py](tests/test_recovery.py), [test_agent.py](tests/test_agent.py) |
| Request/token/step/image limits | Budget stops preserve completed work and reject unexecuted actions; image-blocked requests are not counted as sent. | [test_recovery.py](tests/test_recovery.py), [test_agent.py](tests/test_agent.py), [test_vision.py](tests/test_vision.py) |
| Wrong editable role | Error includes fresh role/name evidence; an explicit combobox fill recovers. Native select, custom option click and keyboard submission are also exercised. | [test_recovery.py](tests/test_recovery.py) |
| Repeated failed action on unchanged page | The next identical action is blocked before execution after the configured two failures; no uncertain pending action is invented. | [test_recovery.py](tests/test_recovery.py) |
| HTTP 404, refused connection, closed page | Browser returns explicit failure; fresh evidence is attached or its capture error is disclosed. No old screenshot is presented as current. | [test_recovery.py](tests/test_recovery.py) |
| Expired login while awaiting approval | Restored state differs, so the approved submission is not executed; the model can ask for help. | [test_recovery.py](tests/test_recovery.py) |
| Approval rejection, wrong ID, changed transaction, interrupted submission | No rejected/stale action is executed, and an already-consumed approval cannot be replayed. Uncertain interruption requires an operator note. | [test_approval.py](tests/test_approval.py) |
| Stale file/browser evidence | Modified files or changed browser state cannot be cited as valid completion evidence. Resume obtains fresh evidence. | [test_agent.py](tests/test_agent.py), [test_browser.py](tests/test_browser.py), [test_state.py](tests/test_state.py) |
| Evidence preservation | Original snapshots survive context compaction; errors/recovery stops are retained for replay. Export preserves referenced assets and excludes browser session storage. | [test_recovery.py](tests/test_recovery.py), [test_approval.py](tests/test_approval.py), [test_replay.py](tests/test_replay.py) |
| Source/count/order and per-item extraction | A changed source, wrong count, skipped prefix, missing item or changed last item is rejected. Duplicates/DOM order are preserved, output comes from the record, heading-only completion fails, and provenance survives interruption. | [test_extraction.py](tests/test_extraction.py) |
| Complete price comparison | One fare cannot complete a multi-item comparison. Wrong selected class/date, loading, changed source/inventory and an outdated managed report are rejected. Every pending item must be resolved; the minimum and tied minima come from recorded prices. Checkpoint/resume retains coverage. | [test_comparison.py](tests/test_comparison.py) |
| Repeated card-level buttons | An exact role/name can be scoped to a distinctive text fragment from the current browser observation. A unique matching parent is required; ambiguous or unobserved contexts fail. | [test_browser.py](tests/test_browser.py) |

Run from the project directory in Git Bash, with existing dependencies installed:

```bash
source .venv/Scripts/activate
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python -m unittest discover -s tests -p test_recovery.py -v
python -m unittest discover -s tests -p test_extraction.py -v
python -m unittest discover -s tests -q
```

The optional real desktop input test still requires `RUN_DESKTOP_TESTS=1`; it moves
the pointer and types in a temporary editor. Ordinary unit tests do not do that.

For this extraction milestone, the final full suite ran 83 tests: 82 passed and
the opt-in desktop input test was skipped. An earlier full run encountered
Windows `WinError 5` while atomically replacing a checkpoint in an existing
approval test. That test passed in isolation and the subsequent full suite passed
without adding a retry or suppressing the error. The cause of the access denial
is unconfirmed; successful reruns do not prove that Windows file-access contention
can never recur.

## Recovery procedure

1. Inspect `python main.py status RUN_ID` and `python main.py replay RUN_ID`.
2. For a provider error, review its reported cause/cooldown and explicitly resume
   when ready. Failed requests can consume quota without reporting token usage.
3. For an uncertain interrupted action, inspect its actual result and provide
   `resume RUN_ID --note "observed outcome"`. Do not resubmit blindly.
4. For a repeated browser failure, correct the control/approach before resuming.
   Changing the page or arguments is different from blindly retrying the same call.
5. Increase total budgets only after reviewing the reason for exhaustion. The
   response crossing the token ceiling has already consumed its reported tokens.

The only optional evidence fallback is after a browser error: if fresh capture also
fails, the result exposes `observation_error` and explicitly states that fresh
evidence is unavailable. No old observation is substituted and no action is retried.

## Practical limits and PS alignment

- Model planning, route/date selection and natural-language summaries still need
  real task validation. Scripted control tests do not prove the model will choose
  the right control on a new website.
- The repeated-failure check tracks failed actions/assertions since corrective
  browser actions, and invalid finishes since new valid verification. It does not
  catch all successful-but-wrong actions, invisible server changes or every loop.
- The browser adapter remains single-page, without iframe targeting, tab switching,
  file uploads/downloads or support for every custom widget. Desktop tools are an
  explicitly enabled alternative, not an automatic fallback. Browser-only mode
  intentionally excludes desktop and local tools.
- Approval gates cover configured browser calls, not every equivalent route to a
  consequential effect. Keyboard Enter/Space may submit and must be considered in
  policies. This is not a security sandbox or a server-side transaction guarantee.
- Sessions can expire. Session storage, live page memory and unsaved forms are
  not restored. URLs that perform side effects on GET are unsafe to reload.
- Every-step primary-screen evidence requires `--record-screen`; capture can fail
  and detached recording gaps are not covered. External phone video, qualifying
  ticket/PNR evidence and submission artifacts are still outstanding.

This work follows the PS's generic harness, skills, plan/act/observe/verify,
human handoff, replay and rehearsal requirements. See
[Do You Know How to Train?](../Hackathon%20PS/Do%20You%20Know%20How%20to%20Train_.pdf),
especially "Every harness must have", the recovery note and "What To Submit".
Task-specific procedures stay in skills; this milestone adds no booking logic.

Implementation reference: Microsoft Playwright,
[role locators](https://playwright.dev/python/docs/locators#locate-by-role) and
[Locator.fill](https://playwright.dev/python/docs/api/class-locator#locator-fill).
