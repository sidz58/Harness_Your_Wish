# Local mock transaction with human approval

Use only the local mock transaction demo URL supplied by the user. This fixture
uses demo credits and a mock username; it does not use real credentials or money.

1. Open the supplied URL and inspect the page.
2. If signed out, fill Demo username with the user's supplied name and click Sign in.
3. Fill Recipient and Demo credits with the user's requested values, then click
   Prepare transaction. Inspect the pending transaction and check both values.
4. Request the normal browser_click on Confirm mock transaction. The operator's
   approval policy intercepts that action. Do not substitute ask_user for approval
   or find another route around the policy.
5. On resume, inspect the restored session and the harness's pending-action result.
   If the approved action already executed, do not click it again. Verify the exact
   receipt and the confirmed transaction count before finishing.
6. If the page changed and approval became stale, inspect and prepare the correct
   transaction again. Only a new approval can authorize its confirmation.
7. Rejection cancels the run. Do not submit another transaction or seek approval again.

Only browser_verify results are completion evidence for this browser task.
