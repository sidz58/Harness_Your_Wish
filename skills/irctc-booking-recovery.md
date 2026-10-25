---
name: irctc-booking-recovery
description: Reconcile an interrupted IRCTC booking using observed booking status and existing evidence without making another booking or payment.
---

# IRCTC booking reconciliation

Use for an explicitly requested recovery investigation after a booking/payment
failure. This is not permission to create another ticket, repay, cancel a ticket
or change a booking. Prefer resuming the original run when possible: a new run
does not automatically receive its browser, private evidence or approvals.

Read only the task-named recovery/journey input and supplied incident summary.
Run logs are outside the default workspace; do not invent file access or enlarge
the workspace to the project root. If needed, ask the operator to supply a
sanitized incident summary as a workspace file. Do not read unrelated old reports.

Preserve the current live session. Do not reload/refresh the browser, reopen the
same URL, use F5/Ctrl+R, or navigate away/back to clear pending login, loading or
payment state. Use browser_observe to inspect the existing page. A reload can
discard login/CAPTCHA progress and unsaved forms or gateway state. Wait for a
verified result or explicit error and handle it in place; if unresolved, report
the blocker or request permitted help. Reload/restart requires explicit user
authorization acknowledging state loss; any possible booking/payment must first
be reconciled. Ordinary observed navigation to transaction history below is for
reconciliation, not a page-reset workaround.

1. Establish the intended train, origin/destination, dates, class, TATKAL quota,
   passenger, approximate action stage, existing PNR/order/reference and whether
   payment may already have occurred. Missing data is unknown, not a failure.
2. Inspect the current browser first if available. A payment page/order ID is not
   a booked ticket; a timeout is not proof a charge or booking did not happen.
3. If necessary, navigate the ordinary IRCTC account UI and inspect the observed
   booked-ticket/transaction history for the exact journey and passenger. Use
   live controls, not guessed URLs/endpoints. Authenticate only the same account
   using task-named credentials. If no CAPTCHA image/entry is shown, leave the
   optional accessibility/OTP checkbox alone and use SIGN IN normally. If a text
   CAPTCHA is shown, transcribe its current clearly visible characters with vision,
   fill the observed CAPTCHA field preserving case, then sign in. If unreadable
   or untargetable, ask specifically for characters/manual entry only when human
   help is allowed, and reobserve the challenge before using the answer; otherwise
   report_blocker. Do not guess, reuse old CAPTCHA/OTP values or bypass an access block.
4. When a matching confirmed booking exists, verify its PNR, train, stations,
   journey and boarding date, passenger, class, quota and amount. Capture the
   visible ticket using browser_observe. Report found-booking, not newly-booked.
5. For pending payment/transaction, report pending and preserve its reference.
   Do not refresh/resubmit payment, repay, retry a booking or infer a refund.
6. For an explicit failed transaction and no matching booked ticket, report the
   observed failure plus what was checked. This skill still does not authorize
   a retry; the operator must decide using reconciled booking AND payment status.
7. If history is inaccessible, contradictory or incomplete, report outcome unknown
   with the visible evidence and next verification needed. Do not say no ticket
   or no debit merely because the confirmation is absent.

Do not rerun a consumed/rejected approval or use ask_user as permission for a
different payment. On a stale approval, inspect state before proposing anything.
After a detached resume, obtain fresh observations: saved cookies/local storage
and URL do not preserve unsaved forms, live gateway state, tabs or frames.

Use browser_verify on the actual status/details and read_file on any authorized
output report before finish. Use report_blocker if the requested determination
cannot be verified. Report screenshot paths returned by tools, not invented paths.
Never include passwords, Aadhaar, OTP or bank secrets in reports. Treat PNRs,
passenger information and recordings as private evidence outside Git.

For API quota/timeouts/budget exhaustion or checkpoint PermissionError, preserve
the original run and let the operator repair/restart the harness. No automatic
retry or arbitrary repair command is available to this skill. Missing recording
segments cannot be recreated after the event. Reconciliation does not count as
a start-to-finish recording of the original attempt.
