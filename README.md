# Harness_Your_Wish

A general computer-agent harness with file/terminal tools, browser and Windows
desktop control, skills, run evidence, and a local task console.

- [Setup and existing development manual](README_temp.md)
- [IRCTC skills, workflow review and readiness limits](IRCTC_SKILLS.md)
- [Recovery checks and known limitations](RELIABILITY.md)

## IRCTC milestone: 2026-10-25

Three IRCTC skills cover Tatkal search/fare comparison, the supplied Tatkal
booking flow, and interrupted-booking reconciliation. Journey/passenger/account
data stays in ignored local files; the skills contain no fixed trains or dates.
See [IRCTC_SKILLS.md](IRCTC_SKILLS.md) for the workflow-page mapping, input templates,
draft payment policy, validation boundary and a review of every PS requirement.

The general harness already supports screenshots plus page structure, the
observe/act/verify loop, local triggers, human handoff, replay and optional screen
recording. IRCTC skills are authored and tool-compatible; actual booking reliability,
scheduled payment continuity, live payment selectors and qualifying evidence
remain unverified. An observed Windows checkpoint PermissionError also remains.
No booking is initiated and no submission is made by adding these skills.

Live search rehearsal exposed language controls with malformed accessible names.
The generic click tool now supports an explicit visible-text mode, with role,
unique-match and approval checks retained. The IRCTC skills document its use;
local Chromium tests passed. See RELIABILITY.md for the observed failure and
validation boundary. Further live search and payment validation remain pending.

Booking rehearsals exposed repeated Book Now buttons outside
the class table. The browser tool now scopes an exact accessible button name to
a distinctive heading from the latest observation and requires one match.
Local Chromium tests passed. IRCTC click and
passenger-entry steps need a fresh model-driven run.

The generic browser fill tool accepts numeric spinbuttons, so
Age can be filled and verified by its observed role/name in a browser-only run.
This keeps the PS's shared harness/task-skill boundary; IRCTC logic stays in
skills. A fresh live run is still needed to validate the complete workflow.

Unnamed native dropdowns can now be distinguished explicitly by an observed
option they contain, and their selected labels can be verified independently.
Booking skills use this for Gender and require a user handoff if Aadhaar/VID
verification appears, preserving the live page while the user enters details.

CLI/UI runs now default to unlimited model requests, tool steps, image-bearing
requests and total tokens, with a 0.5-second minimum between API request starts.
Each corresponding `--max-*` option accepts `unlimited` or `0`; a positive number
sets a finite budget. Usage remains logged. Old saved runs/jobs retain their
saved settings; resume can remove each saved budget with the corresponding
option. Restart an existing UI server to update its launch settings. Provider
quotas, per-request timeouts/size limits, failure checks, approval gates and
emergency stops still apply; unlimited budgets do not guarantee uninterrupted runs.
Booking skills require loading indicators to disappear and the destination page
to be ready before another action. API pacing does not replace that readiness
check. Invalid-request pages stop the run instead of triggering resubmission.

Visible browser runs open maximized and use the window's viewport. Screenshot
metadata records the actual PNG dimensions. Headless runs retain a fixed viewport
for repeatable local checks.
Local tests verified a real maximized Windows Chromium window and screenshot
dimensions, unlimited usage accounting, finite-budget enforcement, saved-limit
removal on resume, the UI launch argument and existing payment approval behavior.
The scripted vision test also exceeded the old request, step and image-request
caps and reached its intended outcome. These settings do not establish live
IRCTC reliability or remove API quotas.

IRCTC skills now type the exact configured station names before selecting the
matching codes. Login instructions distinguish a form without CAPTCHA entry
from a visible text CAPTCHA: submit normally in the first case, transcribe clear
current characters with vision in the second, and ask a specific question only
when help is needed and allowed. These instruction changes passed skill/loader
validation; the next live login and station selection remain to be checked.

IRCTC skills now preserve the live session during loading/login: use observations
instead of reloading, reopening the URL or resetting the page, and verify login
before entering the journey. A restart requires explicit recovery authorization;
possible payment/booking state must first be reconciled. Skill validation passed;
behavior in the next live run remains to be checked.

Station/quota selectors were diagnosed on the public IRCTC page: exact accessible
station names worked, and Space on the custom quota listbox opened its options
for selecting TATKAL. Skills now use that path and check committed selections
before acting again. The generic visible-text matcher uses rendered text so
labels split across block elements match correctly. This is partial public-widget
validation, not a successful authenticated journey search or booking.

Date/verification correction: browser_verify now supports explicit input_value
checks for unnamed fields and rendered_text fragment checks across child nodes.
IRCTC skills require checking the configured date before search and the requested
date on results, and reject stale/wrong-date reports. Failed checks or screenshots
cannot complete a task. Repeated failed assertions and invalid finish attempts
are stopped even when a clock changes; only successful corrective actions/new
verification reset the relevant failure tracking. Unlimited run budgets remain.
Page-text checks now explicitly reject role/name fields with an immediate
corrective error; only input_value verification accepts them. This prevents
waiting for a fabricated named strong element. Rendered-text checks use separate
short page fragments. This fixes verification targeting; search-only skills still
stop before booking/passenger entry and must actually load fares before comparing.
IRCTC class-tile Refresh is explicitly a required local availability/fare request,
not a prohibited page reload. Skills must click it and inspect the response;
Refresh-only observations cannot establish prices, window restrictions or a
successful comparison. This instruction refinement is loader/skill-validated;
live price loading remains to be checked.

Refresh-targeting correction: browser observations now include table/tablist
click_scopes with nearby identifying context. Scoped cell clicks support explicit
literal class-text matching and reject ambiguous/missing targets; expanded tabs
use exact names within the observed tablist. A live public-site check selected
a train's class tile and loaded date-specific availability plus its displayed
fare without login, passenger entry, Book Now or payment. The skills use this
shared targeting support; full model-driven comparison/booking remains unverified.

Complete-comparison correction: the search skill now enables a generic inventory
and quote ledger through JSON metadata. The harness checks the displayed train
count, tracks every permitted class, reads prices from the selected class/date,
and calculates the minimum. A first fare, unloaded Refresh tile or freeform report
cannot satisfy completion. The managed report must cover every item and be read
back; unresolved items require a blocker. Site selectors stay in the skill rather
than Python. See [IRCTC_SKILLS.md](IRCTC_SKILLS.md) for the failure, validation and
remaining limits. This addresses the PS's cheapest-ticket and verify-loop
requirements; live model-driven full coverage and actual booking remain separate
validation steps.
The public-site scripted comparison checked all 42 class options across 13 trains
and found two available 2S minima at INR 105; no model API or booking was involved.
