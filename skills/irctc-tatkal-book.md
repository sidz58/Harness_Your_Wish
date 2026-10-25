---
name: irctc-tatkal-book
description: Follow the IRCTC Tatkal journey and passenger flow, select IRCTC iPay New, and hand payment to the user with verified outcome evidence.
---

# IRCTC Tatkal booking

This skill describes the supplied UI flow; it does not authorize a booking by
itself. Read the journey file named in the task. Do not use example identities,
trains, dates, fares or availability from the workflow PDF. A new invocation is
not permission to retry an earlier payment or buy a second ticket.

## Inputs and operating boundary

Require explicit origin/destination names AND station codes, booking_date_ist,
journey_date, TATKAL quota, allowed_classes, max_total_fare_inr, tie_break,
passenger_file, credentials_file, mode and booking_report_file. Read only those
named private files; do not scan unrelated workspace notes. The passenger file
supplies exact legal name, age for the journey, gender, nationality, contact and
berth preference. It may separately supply authorized account-authentication
details; do not confuse the account holder with the travelling passenger.

- mode rehearsal: stop before Book Now. No identity-verification submissions or
  payment. Report observations and remaining blockers; never book as a test.
- mode book: requires an explicit booking instruction in this run's task, not
  just the JSON value. Check all inputs before entering the booking flow.
- A qualifying PS run is for one team member, one ticket, the member's own
  account, the specified route and next-day journey. Additional human help costs
  points under the PS. Missing prefilled inputs in that mode are blockers;
  a development rehearsal may use ask_user. The user completes final payment at
  the manual handoff described below.

Check journey_date is the next India calendar day after booking_date_ist for a
next-day request. Confirm the live site's date. Do not use a UTC run timestamp as
India's date, or keep a journey date fixed from these examples. Verify the train's
origin departure date for Tatkal eligibility, not just the boarding date.
IRCTC's FAQ lists AC opening at 10:00 and non-AC at 11:00, India time; verify
the selected train/class and its origin date. Do not apply the PS's 11:00 target
to every class. The schedule must be arranged by the operator before freeze;
there is no precise clock/wait tool available inside this skill. Never book a
different date or quota when the requested window has not opened.

The payment workflow ends with selecting IRCTC iPay New and a live ask_user
handoff. The user performs payment directly. Do not click Pay & Book or Pay Now,
press a submission shortcut, or use another tool/URL to initiate payment. An
existing approval policy does not change this task's manual handoff boundary.

Use the browser's observed exact role/name with screenshots as context. Repeated
class names, Refresh, dates and Book Now can be ambiguous across train cards.
For an exact accessible-name control repeated on the page but outside an observed
table/tablist, use browser_click with `scope_text` set to the exact distinctive
heading visible in the latest browser_observe result. For example, target role
button/name `Book Now` with scope_text equal to the selected train's observed
heading. The harness searches that control's nearest parent containing the text
and permits the click only when exactly one matching control remains. Do not use
contains_text for buttons or guess a class-table scope for a card-level action.
Do not choose an arbitrary match, invent a selector, run hidden API requests,
inject scripts or switch to desktop as a workaround. If current tools cannot
uniquely target the intended control, report_blocker with its context. Desktop
actions are not covered by browser approval policies.

## 1. Enter the site and search

Open the website once at the start and preserve that live page. Do NOT reload,
refresh the browser, reopen the same URL through browser_open, press F5/Ctrl+R,
or navigate away/back to clear a spinner or pending login. A reload can discard
login/CAPTCHA progress and selected journey/passenger/payment state. After SIGN
IN, use browser_observe on the existing page to establish signed-in status or a
specific error. Never clear a pending login with navigation or continue into
journey entry without verifying the signed-in account. If progress is unclear,
use a permitted specific handoff or report_blocker while preserving the page.
After a successful login, continue on that same live page. Never refresh/reload
it, reopen it through browser_open or press F5/Ctrl+R; the signed-in session can
be lost. While the next screen loads, use browser_observe instead.
Only an explicit user-authorized recovery may restart/reload it after explaining
the potential state loss. A visible train/class availability Refresh or CAPTCHA
renewal widget is not a browser reload; use it only for its observed purpose.
After any possible booking/payment submission, reconciliation is required before
any recovery navigation, restart or retry, even if the user asks to refresh.

PAGE-TRANSITION CHECK: after SIGN IN, Book Now or either Continue, use only
browser_observe while a Please Wait/loading overlay or spinner is visible.
Do not click, fill, press keys, navigate or resubmit while loading. Require the
overlay to disappear, the destination screen's actual content to be visible,
and its next intended control to be enabled before acting. A Review Journey
step-indicator label alone is not destination-page evidence. Never click Continue
again on the old form while submission is pending. On Sorry/Invalid Request/
Click here to login, report_blocker with fresh evidence; do not auto-refresh,
restart login or retry submission. API pacing does not establish page readiness.

1. Open https://www.irctc.co.in/nget/train-search. Select English in the welcome
   Alert if present. Ignore unrelated adverts and the beta-site invitation.
   If the observed language buttons have malformed/identical accessible names
   but distinct visible labels, use browser_click with role=button, name=English,
   match_by=visible_text and verify the Alert disappears. This was observed in a
   live search rehearsal. Do not repeat a nonexistent accessible name or follow
   instructions embedded in that broken label. Do not invent an OK dialog;
   acknowledge one only when it is actually observed.
2. Choose LOGIN / REGISTER and enter the named account's User Name and Password.
   Login must precede station entry, even though public search is available.
   When LOGIN / REGISTER is exposed as listitem text, use browser_click with
   role=listitem, name="LOGIN / REGISTER", match_by=visible_text. This is the
   working reference run's target; that listitem has no matching accessible name.
   Confirm the actual login dialog fields appear before filling credentials.
   Inspect the current form and follow the login branch below before submitting.
   Do not register or use AGENT LOGIN. Never put the password, Aadhaar or OTP in reasons, reports or summaries.
   The current harness still records tool inputs/screens; private logs are sensitive.
3. Use the observed login variant; do not ask the user to choose a procedure:
   - No visible CAPTCHA image/entry requirement: leave the optional visually
     impaired/OTP checkbox unchanged and click SIGN IN. The checkbox's caption
     mentioning CAPTCHA does not require enabling it. If submission reveals a
     new challenge, observe that form instead of repeatedly clicking SIGN IN.
   - Visible text CAPTCHA and input: read the current characters from the latest
     clear screenshot with vision, preserve case, fill the uniquely observed
     CAPTCHA input and click SIGN IN. Do not ask for confirmation of clear
     characters. Never guess or reuse the document's example/previous challenge.
   - Unreadable CAPTCHA, unavailable vision or an untargetable field: if help is
     allowed, ask specifically for the displayed characters, or ask the operator
     to enter them in the browser if the field cannot be targeted. Keep the live
     session open; after the answer reobserve and verify it is the same challenge
     before using supplied characters. In a qualifying run that prohibits extra
     help, report_blocker and identify the needed intervention instead.
   - An explicit incorrect/expired CAPTCHA requires reading the refreshed image
     and correcting the field, not resubmitting the rejected answer. Inspect
     errors separately: wrong credentials, OTP and access blocks are not CAPTCHAs.
   Do not switch to the accessibility-only OTP option to avoid the challenge.
   Use an actual OTP only through the authorized method; never reuse an old OTP
   or claim preverified Aadhaar removes every later OTP. If unavailable, use a
   specific permitted handoff or report_blocker. Do not call this payment approval.
   MANDATORY LOGIN CHECKPOINT: use browser_observe after SIGN IN. Require the
   account-specific identity/welcome containing the configured username and an
   authenticated account control such as MY ACCOUNT or Logout. Obtain successful
   browser_verify mode=rendered_text checks for the exact observed identity and
   account control. Do not include passwords in verification text. A closed
   dialog, generic welcome Alert, click success or visible search form is not
   proof of login. If LOGIN / REGISTER remains visible or checks fail, resolve
   login/challenges or report_blocker. Do not enter stations/date/quota or search
   until verified. Recheck the authenticated header immediately before Search
   Trains and recover login on the same page if the session was lost.
4. Fill From with origin.name and To with destination.name EXACTLY as stored in
   the journey JSON, including suffixes, punctuation and case. Do not shorten a
   full station name to its city or replace it with a code for searching. Select
   the exact STATION entry and verify its configured code even when there is only
   one suggestion. Saved Journeys/nearby stations are different choices. If the
   exact query has no matching station, report/ask about the observed mismatch;
   do not silently broaden the query or substitute the route.
   Use browser_click role=option with the exact ACCESSIBLE NAME shown in the
   snapshot, in default accessible-name mode. The English button's broken-name
   workaround is not the default for station options. If suggestions have not
   appeared, observe or press ArrowDown on the observed searchbox and inspect
   its options. After a successful click or Enter, verify the updated station/code
   value and observe if needed; do not click an option again after it was selected
   and disappeared. Enter is only appropriate for the observed intended selection.
5. Set the requested date in DD/MM/YYYY using the observed editable field or
   calendar; check the month/year and final value. Leave Flexible With Date off.
   The live form exposed an unnamed textbox; its DD/MM/YYYY * caption is not an
   accessible name. With that observed structure, use browser_fill role=textbox,
   name="", text=<journey_date converted to DD/MM/YYYY>, then press ArrowRight
   followed by Tab on the same control to commit the calendar's internal value.
   The live widget reverted fill-plus-Tab alone; this key-event sequence was
   checked on the public form. Verify the final value in every run,
   using browser_verify mode=input_value on the same role/name and required
   value. Do not click an input by its displayed value or target the caption.
   An actually named field uses its observed name; multiple unnamed matches must
   not be guessed. Do not press Search Trains if this date assertion fails.
   Use All Classes for an unrestricted search. Select TATKAL, not GENERAL or
   PREMIUM TATKAL. Do not enable concessions without the passenger's eligibility.
   The observed quota control is a custom listbox input named GENERAL. Open it
   with browser_press role=listbox, name=GENERAL, key=Space, inspect its options,
   then browser_click role=option, name=TATKAL using the default accessible-name
   mode. Verify the control's new name is TATKAL. If already TATKAL, leave it.
   Use the actual current observed label if different. Do not guess a GENERAL
   button, use visible-text targeting on the input, or call browser_select on
   this custom widget. Only an actual native select uses browser_select.
6. Click Search Trains only after the required date value was checked successfully.
   Verify the station pair, required journey date and quota on the results using
   browser_verify mode=rendered_text on separate actual fragments. These text
   checks take ONLY mode, text and reason, never role/name. A `strong:` snapshot
   line does not expose a named control. For a configured 2026-10-26 journey, use
   `browser_verify(mode="rendered_text", text="26 Oct 2026", reason="Check requested results date")`;
   derive other dates from the journey input. Verify each station name and
   `For Quota | Tatkal` similarly in separate calls, omitting role/name entirely.
   The summary is split across nodes and contains an icon: do not invent a combined heading,
   arrow, weekday or result count. Compare against the configured date, not a
   stale default on the page. If results are for another date, correct the field
   and use Modify Search in place, then reverify both the field and result date.
   Do not reload, compare the wrong date or proceed to Book Now with a mismatch.

Do not invent run_command shell/pyautogui actions to click browser controls.
Only configured commands can run; use supported observed browser interactions
or report the unresolved control. Do not repeat a selector that just failed
unchanged or continue past an unverified station/quota choice.

## 2. Establish the cheapest eligible choice

Refresh INSIDE a train's class/availability tile loads availability and fare for
that train/class; it is NOT a browser/page reload. Clicking the intended tile or
its observed Refresh control is required and permitted. After it returns, inspect
the requested date and actual displayed fare before comparing candidates. Do not
infer an opening-window restriction from the word Refresh or finish after merely
listing tiles. Use the exact observed tile/control role/name; a repeated generic
Refresh label is not a unique target. If it cannot be targeted or its data request
fails, report the real blocker rather than claiming comparison or cheapest fare.
The initial class tiles were exposed as role=cell. Select the intended train's
table from the observation's click_scopes/context, then use browser_click with
role=cell, name=<observed class label>, match_by=contains_text and that returned
scope_id. The train name identifies the table; do not put it into the cell name
or guess a Refresh button. After loading, observe again because expanded controls
may replace the table. Do not use partial-text cell targeting for payment;
payment submission belongs to the user after the iPay New handoff.
Expanded class controls use role=tab. Select the intended train's tablist from
click_scopes/context, then click its exact observed class name with that scope_id.
After each change inspect the requested date's availability and actual fare;
do not reuse a table scope that disappeared when availability expanded.

Inspect every result, including below the viewport, and each permitted Tatkal
class for the requested date. Use class/Refresh controls only when uniquely
targetable. Compare observed fares across trains, not just within one card.
Do not assume the first/leftmost class is cheapest, or that its unavailability
makes another class unavailable. Ignore green availability on other dates.
Never use an old seat count, a General-quota price, or a price guessed from class.

Keep a compact comparison in the authorized report: train number/name, class,
boarding and arrival dates/times, quota, availability, displayed fare, fare basis,
source URL and evidence steps. Record uninspected/unknown candidates explicitly.
Prefer eligible confirmed availability; waitlist/RAC needs explicit task permission.
Apply allowed_classes and any total-price ceiling. An empty class list means all
classes actually offered under Tatkal, not every label in the class filter.
Break a true fare tie using the configured rule. If coverage or comparable prices
are incomplete, do not claim global cheapest or proceed with a guess in a task
requiring cheapest. Report the blocker and lowest observed candidate instead.

Before selecting, obtain a fresh browser_observe of the chosen train, class and exact date.
Click that date tile (orange highlight in the sample), verify the selection and
fare, then use THAT train's Book Now. In rehearsal stop before Book Now.
Availability and displayed prices can change; previous evidence is not a hold.
Never move the journey date, quota, station or passenger to obtain availability.

## 3. Aadhaar authentication, if required

The sample shows Authenticate User with Aadhaar Number / VID, Name, Date of
Birth, Gender, Verify Details and Receive OTP, OTP, consent and Submit. This
may appear at ANY point in the live flow. On seeing it, call ask_user and ask the
user to enter Aadhaar/VID details, consent and any OTP directly in the live
website, then reply when finished. Do not request those values in chat or
read/type them from files. Preserve the same browser/session without refreshing.
After the answer, observe again and verify the website actually authenticated or
advanced before proceeding. A human saying done is not proof. Recheck the
selected journey. If the user cannot complete verification, report a blocker.
Record this additional human intervention honestly for the PS qualification;
do not describe the run as hands-free except final payment.

## 4. Passenger Details

Before entering passenger data, verify the journey strip: train, stations,
boarding date/time, selected class and TATKAL quota. Later screenshots in the
provided workflow show General; reject that mismatch in this task.

Enter the legal name in Full Name as per Govt. ID, the configured age and the
observed Gender option. Check validation messages; never shorten/change a name
to get around an error without an authorized correction. Enter only the requested
passenger, no extra infant or passenger. For the demonstrated Indian passenger,
leave India and No Preference when they match the input; never assume these
defaults are right for a different passenger. Verify Boarding Station as well.

The Age field is exposed as a `spinbutton`. Use `browser_fill` with
role=spinbutton, name=Age and text set to the exact configured age. Press Tab on
that same control to commit the entry, then verify it with `browser_verify`
mode=input_value using the same role/name and value.
Do not relabel it as a textbox or click its label. Tab moves focus to the next
field; it does not advance to the next page. Desktop control is not needed.

Gender, Nationality and Berth Preference may be unnamed native comboboxes. The
Gender placeholder is an option, not the control's accessible name. For that
observed structure use browser_select name="", containing_option="Gender",
label=<exact observed label matching the configured gender>, then browser_verify
mode=selected_option, name="", containing_option="Gender", text=<same label>.
Do not guess a control index or retry name="Gender". Other unnamed selects need
their own distinctive observed option; preserve them unless a change is required.

Check prefilled Contact Details against the private contact input. Fill the
passenger mobile number if missing. A wrong prefilled value is not acceptable;
correct an editable field or stop if it cannot be verified. Do not change account
contact/identity settings. Leave GST and Other Preferences unchanged unless
explicitly configured, including auto-upgrade, reservation choice and coach.
Do not add optional paid products. Inspect and report any preselected insurance
and its charge; obey an explicit insurance preference rather than silently changing it.

After filling and verifying the passenger name, age, gender, contact and other
required details, leave the passenger-form Payment Mode radio buttons unchanged.
Do not select Pay through BHIM/UPI, try to target its radio/row, or force a saved
BHIM/UPI preference into this form. Click the observed Continue directly and
verify the next page is Review Journey. If the site reports a required missing
selection or validation error, report that actual blocker; do not silently
select a different payment mode or repeatedly submit.

## 5. Review Journey and gateway selection

On Review Journey, independently check the exact train/route, boarding date,
class, TATKAL quota, availability, passenger name/age/gender, boarding station,
contact and Fare Summary. Reconcile Ticket Fare, convenience fee/tax, insurance
and Total Fare. Use live values; do not copy the sample's General price. Enforce
the configured maximum against the total, not just the ticket fare. A fare change
that invalidates the chosen cheapest comparison must be resolved before proceeding.

Use the observed Continue on Review Journey to reach Payment Methods only after
those checks. On that page, select the exact observed IRCTC iPay New gateway.
Observe again and verify the gateway selection, displayed charges and journey
summary. Do not select the passenger-form UPI radio or switch payment gateways.
If iPay New is absent or the total cannot be verified, report the actual blocker.

## 6. Hand off payment and verify the result

Immediately after selecting IRCTC iPay New, call ask_user with the verified
journey and displayed total, asking the user to take over payment directly in
the open browser and reply when finished. Stop all payment actions while waiting.
Do not click Pay & Book, Pay Now, request or enter a UPI PIN/bank password/payment
OTP, or submit a transaction. Keep the browser and process open without refreshing.
The user handles all remaining payment screens and confirmations themselves.

Use a live handoff without --detach-on-handoff for this workflow. Scheduled jobs
currently detach; they do not preserve live page memory during that gap, so do
not claim this procedure establishes scheduled payment continuity.

After the user's answer, reobserve; verify the site returned to an IRCTC
confirmation showing successful BOOKED/confirmed status, a real PNR, correct
train/stations, journey/boarding date, class, TATKAL quota, passenger and amount.
Payment success alone, an order ID or the user's assurance is insufficient.
For a pending result, inspect booking/transaction status through the ordinary
site UI; do not start a second booking. If there is no verified confirmed ticket,
report pending/failed/unknown honestly instead of finish-success.

Capture the confirmation with browser_observe; its screenshot path is returned
and saved under the run. Ensure the ticket and PNR are legible; record any fields
needing supplementary screenshots. No screenshot-download tool is available.
Do not rely on email delivery as the PS's ticket screenshot evidence. Do not
claim email access or a ticket PDF download that was not performed.

Write booking_report_file with verified outcome, journey/quota/class, fare
breakdown, selected-candidate comparison limits, PNR, transaction reference,
source URL and evidence step/screenshot paths. Keep this report private. Read it
back; cite its read_file and current browser_verify steps for the ticket details
in finish. Failed assertions and browser_observe are not verification evidence;
correct the failed assertion or report_blocker instead of repeatedly calling
finish. A single heading is insufficient. Every screenshot/report is sensitive;
never put ticket/identity data in the public repository.

## Recovery invariants

- Observe after every failure. An action can take effect before its screenshot
  or checkpoint fails. Never repeat Book Now, Pay & Book, Pay Now, Submit or a
  payment based only on a timeout. First inspect current booking/transaction state.
- For a harmless changed role/dropdown, reobserve and correct the target. Do not
  repeat identical failures or poll rapidly; obey the site's visible cooldown.
  Stop on persistent loading or unresolved ambiguity within the run budget.
- Expired login before any commitment: reauthenticate only the same authorized
  account, then revalidate all journey and passenger fields. Expiry after a
  possible commitment requires transaction reconciliation, not a fresh booking.
- API 429/timeouts, token/image/request budgets, checkpoint PermissionError and
  interrupted recording cannot be repaired by clicking the website again.
  Preserve logs and report the failure. Never claim a complete recording or
  success from missing evidence. The current harness has no automatic API retry.
- Restoring a detached browser restores some storage/URL, not unsaved forms,
  page memory or payment windows. Reobserve and reconstruct only verified safe
  steps. An uncertain payment stays uncertain until reconciled.
- No multiple/borrowed accounts, second ticket, anti-bot workaround or unrelated
  task. If the general tools cannot perform a step, name that limitation.

Sources: user-provided IRCTC Tatkal booking.pdf, pages 1-14 (UI examples);
Syntax Error 2026 PS, pages 1-4 (general harness, handoff, rehearsal and evidence);
IRCTC Tatkal FAQ, https://contents.irctc.co.in/en/TatkalFaq.html (consulted 2026-10-25);
Ministry of Railways, 2026-02-13, https://www.pib.gov.in/PressReleasePage.aspx?PRID=2227511
(Aadhaar/OTP and access challenges). UI examples do not override live state.
