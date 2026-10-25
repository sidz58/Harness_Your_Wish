# IRCTC skills and readiness review

## Unnamed dropdown selection and Aadhaar handoff

Run `20261025T005501Z-38fc890a` exposed three unnamed native comboboxes: Gender,
Nationality and Berth Preference. Selecting name="" was ambiguous; using
name="Gender" was incorrect because Gender is an option, not an accessible name.
The shared browser_select tool now accepts an explicit containing_option hint
from the live observation. No control index or IRCTC-specific Python selector is
used. browser_verify mode=selected_option independently checks the selected
label using the same discriminator. Missing or duplicate matches fail.

The Tatkal booking skill requires ask_user if Aadhaar/VID verification appears at any
stage. The user enters identity details, consent and OTP directly on the website,
then answers in the harness channel. The agent preserves the page and verifies
the resulting state before proceeding. This is an additional human intervention
and must be disclosed when evaluating the PS's hands-free qualification.
The updated dropdown path still requires a fresh live model-driven IRCTC run.

## Restore the browser-only passenger workflow

Rehearsals established a browser-only passenger flow. Desktop login/Age
workarounds were removed from the booking instructions. The shared browser fill
tool accepts the numeric spinbutton role; there is
no IRCTC-specific Age branch in Python. A local Chromium agent-loop check fills
and independently verifies a numeric field without desktop tools. Saved runs
contain skills/settings and evidence, not complete historical source checkouts.
Actual login-to-payment model validation remains outstanding.

## Repeated Book Now button targeting

The attempted General booking run used `irctc-tatkal-book` even though the
results page showed `GENERAL`. The run's tool log records two failed Book Now
targets: the first call used a table-cell-only matching mode for a button; the
second searched globally and matched 13 buttons. Neither click was executed.
The harness then stopped the repeated-failure loop before another call ran.

The test task was: “Search using General quota, pick the first train and its
first class, fill the passenger details, and stop at payment.” The invocation
selected `irctc-tatkal-book`; that task/skill mismatch could have caused later
quota refusals even after fixing the button selector.

General-quota rehearsal materials remain local and are excluded from this
repository. They do not establish the PS's cheapest next-day Tatkal booking.

The generic browser tool now accepts `scope_text` for repeated exact
role/name controls outside observed tables and tablists. It checks that the
heading appears in the latest page observation and that the nearest matching
parent contains exactly one control. Tests cover duplicated controls, stale or
unobserved contexts and ambiguous cards. This solves the target-selection gap at
the harness level; the IRCTC login and booking steps still need a fresh
model-driven run. The full regression suite ran 117 tests: 116 passed and the
opt-in desktop test was skipped.

## Complete price coverage correction

Run `20261024T234116Z-6c60488b` loaded only one train/class fare, then called its
report a comparison while leaving other classes at Refresh. A request to compare
all fares was already present in the skill, so repeating that instruction alone
does not fix the completion gap.

The search skill now opts into shared comparison tools through one-line JSON
`metadata` in its frontmatter. It names the journey input, source fields, DOM
selectors and matching patterns. There are no train names, station codes, dates
or IRCTC branches in the comparison runtime. Changing the site-specific selectors
is a skill-data change; no dependency or model API was added.

- `comparison_begin` freezes every displayed train/class allowed by the journey
  input and checks coverage against the result count. An empty allowed_classes
  means all observed classes, including classes that must be inspected and found
  unavailable rather than silently excluded.
- `comparison_record` reads the selected class, requested date, availability and
  displayed price directly from that train's DOM, with screenshot evidence.
  Another selected class, wrong date, loading response or unresolved status cannot
  count as a quote. The requested date and Tatkal results text are rechecked.
- `comparison_status` exposes every pending item. Explicit unavailable/waitlisted
  date tiles count as checked and ineligible; missing/unloaded prices stay pending.
- `write_comparison_report` requires full coverage and creates the comparison
  table and calculated minimum. The harness rejects finish until this exact report
  is read back. Refreshing a quote invalidates the old report. The final summary
  also uses the calculated minimum rather than a model-supplied price claim.

Use a fresh run after updating; saved runs retain their original skill snapshot.
The metadata currently expects `workspace/irctc_journey.local.json`. Put class
codes in allowed_classes only when intentionally restricting the comparison.
Use a new report filename, or explicitly authorize overwriting the existing one.
The search skill continues to stop before Book Now, passenger entry or payment.

The minimum is among observed available displayed ticket fares for the configured
classes. It is not a held seat or a verified final checkout total. Equal minima
are listed together; the configured tie-break and any total-price ceiling still
need the corresponding journey/checkout evidence. Changing the journey input,
result inventory or source after collection prevents successful completion.
Selectors are based on the observed current UI; a changed UI can require a skill
metadata correction and a fresh run rather than silently accepting partial data.

Local Chromium tests exercise incomplete coverage, a later cheaper class, wrong
selection/date, loading, unavailable outcomes, equal minima, source/inventory
changes, managed-report integrity, checkpoint/resume and Windows line endings.
These tests use synthetic prices and do not establish live model reliability.

A separate public-site scripted diagnostic checked 42 class options across all
13 displayed trains for the configured 26 October 2026 Tatkal search. Every item
was recorded as available with a price or explicitly unavailable. Its lowest
displayed available fare was INR 105, tied between the two observed 2S candidates;
the first INR 1170 quote was not the minimum. Private evidence is retained under
`runs/irctc-comparison-check/results.json` and its screenshots. This diagnostic
used no model API, login, passenger entry, Book Now or payment. It verifies the
current fare controls and quote collection, not a full model-driven run or booking.

Refresh click follow-up (2026-10-25): run `20261024T232910Z-26c57be9` reached
the correct results but targeted class tiles using the wrong semantic role and
without a train container. A hand cursor does not establish role=button; the
observed initial tiles are table cells. Generic browser observations now expose
visible table/tablist click_scopes with nearby context and explicit text-preview
truncation. The agent can click one matching class cell in the intended table
using contains_text, then use exact scoped tab names after expansion. Unknown,
missing, hidden or ambiguous scopes/targets fail rather than selecting a first
match. IDs are opaque observed references and must not be invented. Older scope
previews are pruned from model context with older snapshots; durable logs remain.

A public-page diagnostic used this scoped cell click on an observed train/class
and loaded availability and its displayed INR fare. Evidence is retained privately
under `runs/irctc-refresh-check/`. It did not log in, enter passengers, press Book
Now or pay. This is actual-widget verification, not model-loop reliability or a
claim of cheapest fare. Local tests cover repeated tables/tabs, missing/duplicate
targets and an approved action retaining its scope across inline handoff.

Milestone review: 2026-10-25. The skills follow the user's private
`IRCTC Tatkal booking.pdf`, pages 1-14, and the Syntax Error 2026 problem statement,
especially "What You Build", "Every harness must have", the recovery note,
"What To Submit" and "Terms and Conditions". The private workflow includes
identity/contact/transaction data and is deliberately not copied into this repo.

The initial milestone added skills, input templates, a draft approval policy and
documentation. It added no IRCTC-specific Python code and performed no live login,
booking, identity verification or payment. The source screenshots establish a
procedure, not verified live selectors, prices, inventory or booking reliability.

Live search rehearsal update, 2026-10-25: run `20261024T221811Z-181cff6e`
reached the welcome Alert, but both language buttons exposed an identical malformed
accessible name while their visible labels differed. Repeating an exact-name
English click stopped the run. The generic browser_click tool now supports an
explicit `match_by=visible_text` mode, retaining its role restriction, uniqueness
and approval interception. This is shared targeting capability, not Python
booking logic or an automatic fallback. Both IRCTC skills describe when to use it.
It does not resolve identical labels across multiple train cards.

Login/station refinement, 2026-10-25: type origin.name and destination.name
verbatim, including station suffix/punctuation, then select and verify the
matching station code. Do not replace a configured full name with a city/code
query. The user's login screenshot shows a form without a CAPTCHA entry; in that
variant the skills leave the optional accessibility/OTP checkbox unchanged and
press SIGN IN. The other user-reported variant has a text CAPTCHA: the skills
instruct vision transcription into its observed input when clear, with a specific
human handoff only for unreadable/untargetable challenges when allowed. New or
expired challenges need fresh observation; authentication is verified afterward.
These refinements change skill instructions only. Their model behavior on the
next live login/selection is not yet validated.

Session-preservation refinement: the user's rehearsal `20261024T224806Z-b5cdaada`
reopened the search URL after SIGN IN. All IRCTC skills now forbid browser reload,
reopening the same URL, F5/Ctrl+R and navigation used as a loading/login reset.
They require observing the existing page, verifying login before journey entry
and handling a visible error in place. A deliberate restart requires the user's
explicit authorization and acknowledgment of possible state loss; a potentially
submitted booking/payment requires reconciliation first. This does not prohibit
an observed class-availability Refresh control. The welcome step also forbids
inventing an OK acknowledgement not present in the observed dialog. These are
validated skill instructions, not a runtime navigation lock or a live retest.

Dropdown correction: the next search rehearsal showed station options being
repeatedly targeted in visible-text mode and the quota widget being guessed as a
button/native select. A public-page check (no login, Search Trains, booking or
payment) successfully selected the destination using its exact accessible name,
opened the GENERAL listbox with Space and selected the TATKAL option. The live
station's raw text joined the city and region while its rendered text separated
them with a line break; the generic visible-text matcher now uses normalized
rendered inner_text rather than raw textContent. It still requires one visible
match and does not silently switch strategies. Skills prefer correct accessible
names, verify a selection before trying again, and use the demonstrated keyboard
path for this custom quota control. This validates those public widgets, not the
complete authenticated search, cheapest-fare comparison or payment flow.

Date/evidence correction: run `20261024T230114Z-296ae7fd` failed to fill an
unnamed date textbox because it used the nearby format caption as a control
name, then searched the old date. The skills now specify the actual unnamed
textbox target, commit with ArrowRight then Tab, and require an input_value assertion against
journey_date before search. Results require rendered_text checks of separate
route/date/quota fragments; a copied result count or guessed arrow/combined
heading is not used. A changed field without updated results is insufficient.
The generic verification tool rechecks values/text at completion, retaining
stale-evidence rejection. An old result with only verified_text retains the
original exact-text interpretation. Repeated failed verification/invalid finish
attempts no longer treat changing clocks or new screenshots as corrective proof.
This adds generic verification capabilities; it is not an independent semantic
validator for every IRCTC passenger/fare field or an end-to-end booking guarantee.
The public form was checked directly: fill plus Tab reverted the date, while
fill, ArrowRight, Tab committed the requested value and passed independent
input_value verification. No login, search submission, booking or payment was
performed in that check. This is a validated field-commit procedure, not proof
that every future live run or widget version will behave identically.

Follow-up run `20261024T231622Z-97229558` had the correct date but combined
rendered_text mode with a guessed role=strong/name, so it waited for a nonexistent
named control. Page-text modes now reject role/name immediately with explicit
correction instructions; only input_value accepts them. The skills show the
exact no-scope rendered-text call and require real availability/fare checks after
the header checkpoint. A result-count/Refresh-only report is not fare evidence.
The search skill and the rehearsal task deliberately do not enter passenger
details; booking preparation is a separate authorized stage.

The user's subsequent run reached the correct results but treated Refresh tiles
as unavailable price data and ended as succeeded. Both skills now explicitly
require clicking the intended train/class availability Refresh control: it loads
that tile's data and does not reload the page. The label alone proves neither a
fare nor an opening-window restriction. Actual loaded data is required for price
comparison; targeting/data failures are blockers, not successful comparisons.

## Choose a skill

| Skill | Purpose and stopping point |
| --- | --- |
| `irctc-tatkal-search` | Search and compare the configured route/date/quota; never Book Now or pay. |
| `irctc-tatkal-book` | The complete demonstrated journey/passenger/UPI procedure; rehearsal stops before Book Now. A real booking requires explicit task authorization and a verified approval policy. |
| `irctc-booking-recovery` | Inspect an existing/uncertain booking and payment outcome; never retry, repay or cancel. |

The harness loads one selected Markdown skill per run. Each is self-contained;
no implicit multi-skill loading, external PDF-reading tool or new code is assumed.
YAML frontmatter is descriptive text; the existing loader passes the whole file
to the model. These are this project's skills, not globally installed Codex skills.

## Input files and a search rehearsal

The templates contain no real passenger, account, train, date or price. Copy them
to the existing ignored workspace, then fill the LOCAL copies before running:

```bash
cp examples/irctc_journey.example.json workspace/irctc_journey.local.json
cp examples/irctc_passenger.example.json workspace/irctc_passenger.local.json
cp examples/irctc_credentials.example.json workspace/irctc_credentials.local.json
```

The journey file names the other files. Paths are relative to workspace, not the
project root. Do not point read_file at the Desktop source PDF or run directories.
Use explicit booking/journey dates in India time. In a next-day task, journey_date
must be the next calendar date after booking_date_ist. An empty allowed_classes
list permits comparison of all Tatkal classes offered for that exact journey;
restricting it changes the scope of a "cheapest" claim. null max_total_fare_inr
means no user-supplied ceiling; set a ceiling if required. Empty/template inputs
are not usable data. Keep mode rehearsal for preparation.

For the PS attempt, supply the PS's required stations and the team member's own
account/passenger details in these local files. The reusable skills contain no
fixed route, train, passenger, date, age, fare or availability.

After setup, a search-only rehearsal command is:

```bash
source ~/.bash_profile
source .venv/Scripts/activate
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python main.py run "Read irctc_journey.local.json and search the exact configured journey under Tatkal. Compare observed eligible fares and document coverage limits in the configured search report. Do not press Book Now, submit identity verification, book or pay. Report any blocker with evidence." \
  --skill irctc-tatkal-search --browser --vision --record-screen \
  --max-requests unlimited --max-steps unlimited \
  --max-image-requests unlimited --max-run-tokens unlimited \
  --min-request-interval 1
```

The limits above are run configuration, not measured performance guarantees.
Requests, steps, image-request count and total tokens are unlimited by default;
provider quotas, per-call timeouts/size limits, error checks and approval gates
still apply. Visible Chromium windows now open maximized with
the viewport following the window. Screenshot dimensions come from the actual
saved image, rather than assuming the old fixed viewport.
Repeated-control targeting may block this rehearsal; increasing tokens does not
fix an ambiguous control. Recording requires its optional dependencies and an
unlocked desktop. Do not use headless mode when recording for evidence.

For a pre-booking rehearsal, select `irctc-tatkal-book` with mode rehearsal and
explicitly request stopping before Book Now. These instructions do not start or
schedule a live booking. No actual credentials are supplied by this repository.

## Workflow-to-skill review

| Private workflow pages | Observed UI and skill treatment |
| --- | --- |
| 1-2 | Welcome Alert -> English -> LOGIN / REGISTER -> User Name / Password -> inspect for CAPTCHA entry -> SIGN IN; use the private account file and verify login. The user-reported text CAPTCHA variant is transcribed with vision when clear; unreadable challenges use a specific permitted handoff. |
| 3-4 | From/To autocomplete mixes Stations, saved Journeys and nearby stations; type the configured full names verbatim, then select and verify the exact station codes. |
| 5-6 | Editable DD/MM/YYYY/calendar, All Classes, quota dropdown -> TATKAL; preserve exact date and disable flexible date. |
| 7-8 | Result cards, class/Refresh, per-date availability and fare; compare every eligible candidate, including offscreen results, without using the example trains as defaults. |
| 9 | Select the matching date tile, then that train's Book Now. The later example shows General quota: recheck Tatkal and never continue with that mismatch. |
| 9-10 | Authenticate User/Aadhaar/VID/OTP/consent example; always hand off for the user to complete directly in the live website, then verify the result. Its exact live placement is unverified; extra human authentication is a qualification limitation. |
| 10-11 | Passenger Details, boarding station, contact, nationality and berth preference; use private input, verify fields and validation, add only the requested passenger. |
| 12 | Fill and verify passenger details, leave Payment Mode radios unchanged, Continue, then independently check Review Journey and the complete fare breakdown before its Continue. |
| 13 | Payment Methods -> select IRCTC iPay New -> live user handoff before Pay & Book; recheck route/date/quota/passenger/total. |
| 14 | The user handles the remaining gateway/payment actions directly; afterward independently verify the returned IRCTC ticket/PNR. A gateway order/payment status alone is insufficient. |

Corrections to the source workflow are intentional:

- A leftmost class is an inspection hint, not proof of the lowest fare. One
  unavailable class/date cannot establish availability for another class. The
  comparison must cover all eligible trains/classes before claiming cheapest.
- Later screenshots show General quota and different fares. Those prices cannot
  be used as Tatkal evidence. Availability on another date is not a substitute.
- The example seat counts do not guarantee future availability. A saved screenshot
  is training material, never a live observation.
- The PS's ticket screenshot is required evidence. Email delivery is not a
  replacement, and the harness has no email connector or ticket-download tool.

## Payment policy and handoff limits

`policies/irctc-payment.example.json` is syntactically valid for the existing
harness. It intercepts browser clicks and key presses on button labels
`Pay & Book` and `Pay Now`. Those labels come from screenshot text; their actual
accessible roles/names have NOT been observed on the live page. It is a draft,
not a claim of a verified IRCTC payment gate. Match fields are exact.

Before a live payment attempt, rehearse to the pre-payment page and verify the
actual control/action is covered by a policy. If the live name differs, prepare
and review a corresponding policy before the run; do not click an unprotected
alternate action. A policy is included in the run's saved configuration, so editing
its source later does not update an already-created/queued run. A skill checks
intent; the existing Python harness enforces only configured matching calls.

Current behavior and limits:

- Live UI/inline terminal handoffs retain the same process/browser. The user has
  validated filename answers and mock approval/rejection. Website session expiry
  can still occur while waiting.
- The booking skill selects IRCTC iPay New, then uses ask_user before Pay & Book.
  The user handles the remaining payment actions directly. The sample approval
  policy is retained as a harness example; this skill does not invoke payment
  submission. This handoff is not yet validated as a qualifying PS payment flow.
- Scheduled workers force detached handoffs. The process/browser closes and later
  resume restores storage/URL, not the live form, gateway, sessionStorage or page
  memory. No durable timed payment handoff is established by these skills.
- Browser policies do not protect desktop actions or every equivalent form-submit
  route. The skill forbids bypasses but does not make the harness a sandbox.
- A changed page invalidates approval. Consumed/rejected approval is not reusable.
  A timeout after a payment-capable action requires reconciliation before any retry.
  Approval currently fingerprints the whole accessible page and form values;
  a live clock or changing status text can invalidate it even when the payment
  fields are unchanged. Its behavior on IRCTC needs rehearsal.

## PS requirements and actual status

| PS requirement | Verified implementation / remaining work |
| --- | --- |
| General harness; a new task uses a skill | IRCTC procedure/selectors are in Markdown skills and input/policy data. Shared comparison tools enforce coverage and compute a minimum without IRCTC-specific Python. Live general file/browser/desktop demonstrations exist. |
| Hands: shell, files, browser, desktop apps | Fixed-command shell, confined workspace read/write, single-page Playwright, Windows desktop baseline exist. Repeated buttons can use observed text scopes; iframes and browser file uploads/downloads remain unsupported. |
| Eyes: screenshots plus structure | Browser screenshot + accessibility text and terminal output exist; --vision sends images to the model. Snapshot truncation requires explicit coverage handling. |
| Plan/act/observe/verify loop | Existing loop and evidence checks; skills require exact journey/quota/passenger/fare/PNR checks. Semantic booking correctness is not independently enforced for every field by code. |
| Skills folder | Three IRCTC skills are discoverable by the current CLI/UI; source UI examples are documented above. Live IRCTC validation remains. |
| Chat, schedule, event triggers | Local task console/CLI, foreground schedule worker and file events exist. This is not an email-trigger integration or a guarantee of exact window timing. |
| Human handoff through own channel | Live UI questions/approvals validated against file/mock tasks. Scheduled payment continuity and a single qualifying final-payment interaction remain. |
| Step screenshot, reason, replay | JSONL and replay exist. --record-screen adds every-step primary-screen images when capture succeeds; ordinary browser screenshots alone do not cover file steps. |
| Note: rehearse slowdown, errors, bot checks, model limits | Recovery skill forbids blind booking/payment retries and states blockers. Actual IRCTC failure rehearsal is outstanding. A Windows checkpoint replacement PermissionError occurred in run 20261024T191316Z-2c868482 and is unresolved. |
| Schedule before freeze; next-day cheapest qualifying ticket | No qualifying booking is created or scheduled here. Need complete cheapest comparison, correct passenger/route/quota/date and timed-run rehearsal. |
| One team member's own account; one booking | Explicit skill constraints and private inputs; no multi-account or duplicate-attempt procedure. |
| Submission evidence | Need actual run log, ticket screenshot with PNR, whole-run screen recording, external untouched-device phone video, IRCTC skills and demo video in the designated Drive folder. Replay/export exist, but evidence has not been assembled. |
| Freeze | PS says code and other materials freeze at 09:00; only the designated Drive folder may change afterward. Confirm the organizer's calendar date; do not assume these documents authorize post-freeze edits. |
| Bonus: self-improving/demo-generated skills | Not implemented. These manually authored skills do not establish either bonus. |

The PS recovery note mentions the small number of booking windows, opening-time
errors, anti-bot blocks, a personal hotspot and model rate limits. Prepare the
device/network and configured API limits before the attempt. Do not turn an
access block into an evasion strategy or claim a hotspot guarantees access.
Record missing evidence and additional human help honestly.

## Official references and differences to resolve

- **IRCTC, Tatkal FAQ (consulted 2026-10-25):**
  https://contents.irctc.co.in/en/TatkalFaq.html . Opening-day eligibility is
  based on the train's originating-station date. The FAQ lists AC at 10:00 and
  non-AC at 11:00, India time; the PS's 11:00 target is not the AC time. The FAQ's
  class descriptions are internally inconsistent, so inspect the actual quota
  offered for each train/class rather than hardcoding 1A/EC eligibility.
- **Ministry of Railways / PIB, Aadhaar-Based Authentication, Multi-Layer
  Cybersecurity, and Anti-Fraud Measures, 2026-02-13:**
  https://www.pib.gov.in/PressReleasePage.aspx?PRID=2227511 . Confirms Aadhaar/OTP
  and anti-bot controls. A preverified account does not prove the live flow will
  have no challenge. DOM structure improves targeting; it does not guarantee access.
- **IRCTC, Terms and Conditions (consulted 2026-10-25), General, page 7:**
  https://contents.irctc.co.in/en/Terms%20and%20conditions.pdf . Its automation
  restriction is a service constraint separate from the hackathon's requirements.
  This repository does not implement an anti-bot/CAPTCHA bypass.

## Validation and Git boundary

Checked against all pages of the supplied workflow and the PS, the actual skill
loader/tool declarations, browser approval policy validation, private input path
conventions and adversarial scenarios (wrong quota/date, cheaper uninspected class,
ambiguous repeated controls, stale approval, rejected action, payment timeout and
missing ticket evidence). This is document/tool compatibility review, not a live
IRCTC test or proof of successful cheapest booking.
All skills passed the skill-creator validator using temporary SKILL.md copies in
the ignored review directory, and loaded through the actual project loader. JSON
templates parsed, the draft policy validated and matched its intended click/key
calls, and the existing local Chromium approval regression suite passed. Browser
tests required execution outside the subprocess-restricted sandbox; the initial
sandbox attempt could not launch Playwright. No project dependency was added.

Source, tests, logo, local demo fixtures, requirement files, skills, public empty
templates, draft policy and documentation belong in Git. Exclude `.venv`, browser
binaries, workspace, private input, `.env*`, runs/checkpoints, jobs, exports,
recordings, PNR/tickets, raw workflow PDFs and any credentials. `.local.*`, private/
and secrets/ are ignored; examples use `.example.json` and contain no real data.
The existing long-form development manual remains `README_temp.md`; it was not
renamed as part of this milestone. No commit, push or submission is performed.
