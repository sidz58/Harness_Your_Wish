# Harness Your Wish

Latest IRCTC workflow/PS review: [IRCTC_SKILLS.md](IRCTC_SKILLS.md), 2026-10-25.
That review supersedes older IRCTC readiness notes below. The user has now
validated live UI filename handoff and local mock transaction approval/rejection;
this does not establish real IRCTC payment or scheduled-handoff reliability.

Current milestone: a Python computer-agent harness with a Gemini tool-calling loop,
selectable Markdown skills, optional Playwright browser tools, screenshot vision,
Windows desktop tools, durable CLI handoff/resume, saved browser sessions,
operator-configured browser approval gates, one-shot schedules and file-event
triggers, completion evidence, JSONL run logs, an offline replay viewer, optional
screen recording, portable evidence exports, and a local web task console.
Requires Python 3.12 or newer.
File/terminal runs use only the standard library; browser runs require Playwright and Chromium.
Desktop runs additionally require PyAutoGUI and Pillow.

## Replay, recording, and evidence export

View an existing run, including runs created before this milestone:

```bash
python main.py replay 20261024T094103Z-5d6c1843
```

Open the generated file using the CLI's printed `explorer.exe` command.
The `replay.html` in the project root is a template, not a run viewer.
You can also open the printed `replay.html` in a browser (in Git Bash, `explorer.exe
"runs/20261024T094103Z-5d6c1843/replay.html"`). The page works offline and shows
actions/reasons/results, screenshots, failures, handoffs/resumes, request/token
usage, and video segments when available. Previous/Next and Play navigate the
saved evidence; they never execute actions. Missing images or recordings are
listed explicitly. It cannot recover screenshots or video that were never saved.

Install the optional recording dependencies, then try a no-API recording:

```bash
python -m pip install -r requirements-recording.txt
python main.py demo --record-screen
```

For a live run, append `--record-screen` to your existing command, for example:

```bash
python main.py run "Check the Python version and verify the result." --record-screen
```

Recording captures the **whole Windows primary screen**, including unrelated
visible windows, locally at our configured 5 frames/second, without audio. Keep
the screen unlocked. It starts before browser/desktop initialization and stops
after the agent succeeds, fails, is interrupted, or detaches for a handoff. Inline
terminal handoffs stay recorded while waiting. `resume` retains the original
recording option and starts a separate segment; the detached gap is not recorded.
`--headless` is rejected with recording because the hidden browser would not be
visible. Scheduled/event jobs accept the same recording flag.

When recording is enabled, the harness also saves primary-screen screenshots
before each attempted action and after each returned result, including file and
terminal tools. These supplementary images are local evidence; they are not
automatically sent to the model. Browser/desktop tool screenshots keep their
existing vision behavior. Without `--record-screen`, only those tool screenshots
are captured, so not every step has an image.

The optional `imageio-ffmpeg` package provides an FFmpeg binary; its executable
path is recorded in the log. The package also honors `IMAGEIO_FFMPEG_EXE` if you
deliberately configure another binary. Recording errors fail explicitly, with no
automatic retry or switch. Normal stop finalizes the MP4. The encoder is attached
to a Windows job so it is terminated when the harness process exits; a forced kill
can leave an incomplete segment, which the viewer flags as unfinalized. Recording
failure can occur after task success: the command/job fails and the viewer shows
the evidence error separately from the saved task result.

Export a stopped run (replace `RUN_ID` with the printed ID):

```bash
python main.py replay RUN_ID
python main.py export RUN_ID
# Optional explicit files; repeat --artifact for more files:
python main.py export RUN_ID --artifact workspace/desktop_note.txt
```

Exports go into a new folder under `exports/`, containing `replay.html`, JSONL
events, the saved result, referenced screenshots/videos, logged skill snapshots,
and explicitly attached files. `manifest.json` lists file sizes and SHA-256 hashes
(excluding itself). No entire workspace, saved configuration, or checkpoint is
copied. A failed export is left inspectable and has no completed manifest.
Active runs are locked against replay generation/export. Regenerate after a
resume to see the latest events. Keep the export folder together for portability.

Review before sharing: logs and screen captures may contain file contents, user
answers, login details or other visible information. Export does not publish or
upload anything. A submission still needs the relevant ticket/PNR and external
phone video; this feature does not create those artifacts or certify qualification.

Verification: real local screen capture and MP4 decoding passed using the offline
scripted demo; the exported page was checked in Chromium for image loading, video
metadata, navigation and narrow-screen layout. Unit tests cover export integrity,
HTML injection/path rejection, missing evidence, handoff capture and recording
failure behavior. These checks did not call a model API; a live model run with
recording remains to be tried by the operator.

## Local task console

Start the loopback-only web interface from this directory:

```bash
python main.py ui
```

If your API keys are exported in `.bash_profile`, start the console from **Git
Bash** after `source ~/.bash_profile`. The web server and its child agent inherit
the environment of that terminal. A console started from PowerShell does not
automatically load Git Bash's profile. Stop and restart an existing console after
changing its environment; refreshing the page alone cannot load a new key.

It opens `http://127.0.0.1:8765/` and lets you submit a task to the existing
agent with file/terminal, browser, or desktop access, optionally choosing a
skill, sending browser screenshots to the model, or recording the screen. The
console uses no total run token limit and shows live command output and recent
completed run summaries. Authoritative evidence remains under `runs/`; the
console binds to this computer only.
Live UI runs now wait for question answers and exact-action approve/reject decisions
in the console. The child process and browser stay open, preserving the live page
and unsaved forms. Refreshing or reopening the console reconnects to the active run.
Approval cards show the action, URL and screenshot captured when approval was requested;
the harness checks the page state again before executing it. Duplicate/stale responses
are rejected. Answers currently accept one line, up to 4,000 characters.
Validation: local HTTP tests cover response binding, duplicate/stale decisions and
ended processes. A scripted Chromium UI check passed for reconnecting, submitting
an answer, approving the next action, JavaScript errors and mobile page width.
Existing local Chromium approval/rejection regression tests passed. These checks
do not claim a live-model run or real payment validation.

Select an optional project-relative approval policy JSON path to enable protected
actions (for the local fixture: `browser_demo/approval_policy.json`). No policy means
no action approval gates. Policies cover matching browser actions, not every possible
desktop or alternate submission route.

Keep the console terminal open. Stopping it closes the response channel; a waiting
agent detaches and must be resumed through the CLI, which recreates its browser.
Process crashes and website session expiry are not prevented by live handoff.
Scheduling, replay and export still use the CLI; scheduled jobs still detach on handoff.

To test a question, submit: `Ask me which filename to use, then create that file
containing exactly: Handoff works. Read it back to verify.` Answer in the current-run card.
For approvals, serve the fixture in a second terminal with
`python -m http.server 8766 --bind 127.0.0.1 --directory browser_demo`, select Browser + files,
skill `mock_transaction`, and the policy path above. Request a mock transaction at
`http://127.0.0.1:8766/transaction.html`. Test approval and rejection in separate runs.

UI-launched browser runs use the project's `.playwright` folder unless you set
`PLAYWRIGHT_BROWSERS_PATH` explicitly. The console prints the selected cache at
startup. It does not download a browser or switch caches when a configured
installation is missing. For a fresh installation in Git Bash:

```bash
source .venv/Scripts/activate
source ~/.bash_profile
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python -m pip install -r requirements-browser.txt
python -m playwright install chromium
python main.py ui
```

The pip/install commands are only needed to set up or update browser dependencies.
Restart the console after changes to its code or launch environment.
If the UI reports an older server version, stop the existing server with Ctrl+C,
start `python main.py ui` again, and refresh the page. HTML changes load immediately
but Python backend changes require a restart. The UI checks compatibility before
enabling task submission so mixed versions cannot silently stop status polling.
The console reserves its port exclusively on Windows. Starting another console
on port 8765 fails with instructions to stop the existing server first.

The interface uses the supplied logo in `assets/logo.svg`, local system fonts,
and a responsive layout. It shows whether the server has a non-empty API key and
blocks task creation before spawning an agent when it is missing. This readiness
check does not call Gemini or validate API quota. No credential is sent to the
webpage. Desktop access always includes screenshot vision; browser vision is
optional. Questions detach cleanly and show the CLI command needed to answer.

UI validation: console backend tests cover missing-key rejection, credential
non-disclosure, underscore skill names and failed-process status. Local Chromium
checks cover the supplied logo, responsive layout, setup states, a mocked task
submission and escaped run output. The running console's API-key inheritance was
checked without returning its value. These checks make no model API requests;
a live model task through the polished console remains to be validated by the
operator.

## Try the offline demo

From this directory:

```powershell
python main.py demo
```

This is **a scripted demonstration, not a model run**. It executes the real tools
through the same agent loop, reads notes, checks the Python runtime, writes a
report, and reads the report back before finishing. It makes no network requests.
Each invocation creates a new directory under `workspace/` and prints its location.
Inspect `report.md` there and `events.jsonl` / `result.json` in the printed run folder.

## Run a real agent

The code reads `GOOGLE_API_KEY`. When it is unset, `GEMINI_API_KEY` is accepted as
a compatibility alias. If both are set, `GOOGLE_API_KEY` takes precedence; an empty
primary value fails rather than switching keys.

In Git Bash, load your existing profile and export the variable to Python:

```bash
source ~/.bash_profile
export GOOGLE_API_KEY
mkdir -p workspace
python main.py run 'Check the Python version using the configured command, then finish with the observed result.'
```

Set your Gemini key for the current PowerShell session without putting the key in
command history:

```powershell
$credential = Read-Host 'Gemini API key' -AsSecureString
$env:GOOGLE_API_KEY = [System.Net.NetworkCredential]::new('', $credential).Password
Remove-Variable credential
New-Item -ItemType Directory -Force .\workspace | Out-Null
Set-Content -Encoding utf8 .\workspace\notes.txt 'Build a reusable computer agent. Start with files and terminal tools.'
python main.py run 'Read notes.txt, write a short summary to summary.md, then read it back to verify it.'
```

Use your own existing workspace with `--workspace C:\path\to\task-folder`.
The workspace must exist and must not contain this project's `runs/` directory.
The sample `Set-Content` command above replaces `workspace/notes.txt` if it exists.

The default model is `gemini-3.5-flash-lite`. Override with `--model MODEL_ID` if
your project has access to a different Gemini model supporting function calling.
Account access, free quota, and live model quality require checking with your own
key. Offline tests do not establish live API availability or task accuracy.

```powershell
python main.py run 'Check the Python version.' --max-requests 10 --max-steps 15
python main.py --help
python main.py run --help
python -m unittest discover -s tests -v
```

## Select a skill

From this directory in Git Bash:

```bash
python main.py skills
python main.py run 'Write a runtime report to runtime_report.md.' --skill runtime_report
python main.py run 'Summarize file_check.txt into file_summary.md.' --skill summarize_notes
```

The summary example uses the `file_check.txt` created in the earlier file test.
Provide different source and destination paths in the task when needed.

Add a UTF-8 Markdown file to `skills/` to introduce another procedure. Use a name
such as `my_task.md`, then select it with `--skill my_task`. Describe the inputs,
steps, error handling, and completion checks. Skills use the existing tools;
adding a capability such as a browser still requires a tool implementation.

The selected skill is loaded before a live run, shown in the terminal, and passed
to the model on each request. Its full text and SHA-256 are saved in the
`skill_loaded` event so the run records the exact instructions used. Explicit
user instructions take precedence over skill defaults; tool validation and
completion checks remain enforced by the harness.

Missing, empty, invalid UTF-8, oversized, and out-of-directory skills fail before
any API request. Skill selection is explicit; no skill is automatically selected
when `--skill` is omitted. Skills can be up to 64 KiB. Only select skill files you
have reviewed, since their text is supplied as instructions to the model.

## Browser milestone

Use Git Bash from `Alum_Track`. A project virtual environment and local Chromium
download are used so installation stays separate from other projects:

```bash
python -m venv .venv  # only if the environment does not already exist
source .venv/Scripts/activate
python -m pip install -r requirements-browser.txt
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python -m playwright install chromium
```

Keep `PLAYWRIGHT_BROWSERS_PATH` set in each session using this browser installation.
Start the local form server in one terminal (leave it running):

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory browser_demo
```

In another Git Bash terminal, from `Alum_Track`:

```bash
source .venv/Scripts/activate
source ~/.bash_profile
export GOOGLE_API_KEY
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python main.py run 'Open http://127.0.0.1:8765/. Register Full name Demo User and Email demo@example.com. Submit registration and verify the confirmation includes both values.' --browser
```

The isolated Chromium window opens visibly and closes when the run ends. Add
`--headless` to hide it. Your personal browser profile is not used. Screenshots
are saved under `runs/<run-id>/screenshots/`; the event log links each successful
browser observation to its screenshot. By default, page roles, names, and text
are sent to the model. Add `--vision` to also send the latest screenshot image.

Browser tools: `browser_open`, `browser_observe`, `browser_fill` (editable
textboxes/searchboxes/comboboxes), `browser_click` (role and name),
`browser_select` (native single-select option labels), `browser_press` (declared
navigation/editing keys on a role/name), `browser_scroll` (up/down), and
`browser_verify` (exact visible text). Use observed accessible names. Ambiguous locators fail
explicitly. Observations are capped at 16,000 characters with a truncation flag;
screenshots capture the viewport. Actions wait for Playwright's readiness checks
within a 10-second timeout. There are no automatic action retries in our harness.
A failed action may already have changed the page, so observe before repeating it.
Failed browser actions attempt a fresh snapshot/screenshot and return it alongside
the error. If that capture also fails, `observation_error` explicitly records why;
no older screenshot is substituted. `browser_fill` defaults to `role="textbox"`
for compatibility; the model must explicitly use `role="combobox"` or `searchbox`
when observed. There is no automatic locator fallback. Custom menus use observed
option clicks or keyboard actions; a native select uses `browser_select`.

After browser actions, `finish` requires a successful `browser_verify` step.
The harness rejects evidence from before a later browser action, checks the URL,
and checks that the verified text is still visible. This establishes the stated
visible text, not arbitrary business correctness or server-side persistence.
The local form displays a confirmation using JavaScript; it stores no registration.

This first browser version supports one page and HTTP(S) navigation. It does not
provide tab switching, iframe targeting, uploads, downloads,
or coordinate clicks within the browser adapter. Browser navigation is not a network sandbox: use only
destinations and actions authorized for your task. Page text, entered values, and
screenshots may contain sensitive data and are retained in local run artifacts.

For a task that only needs the web, add `--browser-only` alongside `--browser`.
This exposes browser tools, `ask_user` and `finish`, excluding file/terminal tools.
It cannot be combined with desktop control. General runs still support mixed
browser/desktop/file/terminal tasks when this option is omitted. Tool selection
guidance also asks the model not to read unrelated workspace notes, but only the
explicit browser-only flag enforces removal of those tools.

Run all tests, including real Chromium tests, with the virtual environment active:

```bash
python -m unittest discover -s tests -v
```

Browser tests use a temporary loopback server and scripted model responses, so
they consume no API quota. They explicitly skip if Playwright is absent; with
Playwright installed, missing Chromium or browser failures fail the tests.

Implementation reference: Microsoft's [Playwright Python locators documentation](https://playwright.dev/python/docs/locators)
and [ARIA snapshot API](https://playwright.dev/python/docs/api/class-locator#locator-aria-snapshot).

## Source-constrained list extraction

The live YouTube trial exposed task drift and insufficient evidence: an empty
homepage was replaced with an unrequested Python search, and a saved item lacked
observed support. The exact prompt, command, run evidence and response are recorded
in [RELIABILITY.md](RELIABILITY.md#challenge-youtube-scope-drift-and-insufficient-extraction-evidence).

For ordered web lists, use `browser_extract` instead of reconstructing items from
memory or a truncated page snapshot. Supply the observed source URL, element role,
count, and optionally a container role/name and heading level. The tool reads
rendered text in DOM order, normalizes whitespace, preserves duplicates, and fails
when a requested item is absent/empty. It does not silently skip missing items,
sort results, choose another search, or pad a short list. Native roles/containers
make this general across sites; choosing the right semantic list still needs the
model's judgment. DOM order is not guaranteed to match visual grid order.

`write_extracted_file` accepts an extraction step and path, not arbitrary content.
It rechecks the current source, selection, every item and link, then builds a
numbered UTF-8 list. Its provenance and SHA-256 are checkpointed before writing.
Completion requires both matching current `browser_extract` evidence and a file
readback. Verifying just a page heading cannot certify the extracted report. After
an interruption/resume, extract again and read the existing file before finishing;
an uncertain write requires the normal operator `--note`, not automatic replay.

For strict enforcement, add `--source-url URL --extract-count N`:

- `--source-url` requires browser tools, excludes desktop control, and removes
  freeform `write_file` and `run_command`. Source-derived files use the extraction
  writer. Extraction must match that exact URL and start at the first matching
  item (offset zero). Navigating elsewhere does not change the constraint.
- `--extract-count` requires `--source-url` and accepts our configured range of
  1..100. The model cannot reduce it to hide missing items.
- URL matching normalizes scheme/host case and the empty root path only. Query,
  fragment and path remain significant; use the observed resolved URL when a
  redirect changes it. These settings are snapshotted for resume/scheduled jobs.
- These are declared constraints, not a complete interpretation of the prompt.
  A wrong role/container or different filters at the same URL still need review.
  Ordinary mixed tasks retain their existing file/terminal tools without this flag.
- `--browser-only` is for read-only browser tasks and excludes the extraction file
  writer too. Omit it when asking to save a report.

Example stricter retry using a new filename so the original evidence stays intact:

```bash
python main.py run "Open https://www.youtube.com/. Save the first 6 video titles from that homepage in page order to youtube_report_checked.txt. Use browser_extract and write_extracted_file. If no video list is available, report_blocker with evidence; do not choose another search topic." --browser --source-url https://www.youtube.com/ --extract-count 6 --max-requests 20 --max-run-tokens 80000
```

If requested data is unavailable, `report_blocker` requires real observation step
IDs and ends with a `blocked` result/checkpoint and an explicit `Blocked:` summary.
It is not successful completion and does not fabricate/delete output. The CLI
returns normally after reporting the outcome; inspect its status, not just the
process exit code. `ask_user` remains available when a human can clarify the task.
Changing an operator-locked source/count requires a new run with explicit options;
a model or page cannot weaken the saved contract.

Extraction records, source URLs, per-item values/links, file hashes and blocker
evidence are retained in events/replay. Exports include the log and referenced
screenshots; attach the actual report explicitly with `export RUN_ID --artifact
workspace/FILE.txt`. No new dependencies or website-specific extraction code are
introduced. Local scripted Chromium tests cover the guarantees above. A live
YouTube retry correctly reported the empty homepage feed as blocked without an
alternate search or report file; see [the live result](RELIABILITY.md#live-retry-result).
Successful extraction from a populated live website remains unvalidated.

```bash
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python -m unittest discover -s tests -p test_extraction.py -v
```

## Screenshot vision and desktop control

Activate the project environment in Git Bash:

```bash
source .venv/Scripts/activate
python -m pip install -r requirements-desktop.txt
source ~/.bash_profile
export GOOGLE_API_KEY
```

The dependencies were installed and tested in this project's `.venv`. Use
`--desktop` for Windows mouse/keyboard control; it automatically enables vision:

```bash
python main.py run 'Use Notepad to create desktop_note.txt in the workspace containing exactly: Desktop tools are working. Save it and verify its contents.' --desktop --skill desktop_note --max-run-tokens 40000
```

Keep the desktop unlocked and the intended apps on the primary monitor. Do not
use the mouse/keyboard during the run except to stop it. These tools control
your actual session; they are not an OS sandbox. Screenshots include the primary
monitor, are saved locally, and are sent to the model. Close sensitive windows
before starting. Windows-only at this milestone; multiple monitors, elevated
apps/UAC desktops, and locked sessions are not supported.

**Emergency stop:** press F12, move the pointer to a primary-monitor corner, or
create the `STOP` file in the printed run directory. The stop is latched: the
run fails rather than giving the model an opportunity to continue. A pending
model HTTP request may finish before the process exits, but its actions are
not executed after the stop. Ctrl+C in the terminal also interrupts the run.
An already-started short input action may finish before the next stop check.

Desktop tools:

| Tool | Behavior |
| --- | --- |
| `desktop_observe` | Capture the primary monitor and return an observation ID and dimensions. |
| `desktop_click` | Left/right single/double click using pixels in that screenshot. |
| `desktop_type` | Type literal Unicode text using Windows input events; the clipboard is untouched. |
| `desktop_keys` | Send a key or shortcut, such as Ctrl+S. |
| `desktop_scroll` | Scroll at the pointer position. |
| `desktop_verify` | Record the model's visual assessment of the latest observation. |

Screenshots are reduced proportionally to a maximum edge of 1600 pixels.
Click coordinates are mapped back to the full primary-monitor dimensions.
Actions require the current observation ID and a matching foreground window;
observations expire after 60 seconds. A changed screen size or mismatched
screenshot/monitor size fails explicitly. Actions return a fresh screenshot.
Only one tool call per model response is allowed in desktop mode.

`desktop_verify` is **model visual judgment**, not an independent assertion that
the task is correct. Completion checks its observation ID, age, foreground,
and action revision. It does not compare every pixel or detect every external
UI change. For saved-file tasks, the desktop_note skill also requires a real
`read_file` and content comparison. The harness cannot infer every file written
by a desktop application, so review task-specific evidence.

Browser vision uses the same image transport:

```bash
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python main.py run 'Open http://127.0.0.1:8765/ and describe the visible form. Verify the heading Agent form test.' --browser --vision
```

Only the latest screenshot is included in subsequent API requests. Previous
image bytes are removed from the conversation; their text observations and
local screenshots remain. Provider thought signatures are preserved. This is
an explicit image-history policy, not automatic recovery or a model fallback.
Text history is still retained and bounded by the existing run limits.

Our image defaults are 2 MiB per screenshot and 20 requests containing an image.
Change them with `--max-image-bytes` and `--max-image-requests`. Exceeding either
fails explicitly; no image is silently dropped or compressed again. All reported
token usage still counts toward `--max-run-tokens`; image-request limits do not
guarantee provider quota availability. Logs record image paths, dimensions,
byte counts, and hashes rather than duplicating base64 image data.

### Verification status

Local suite includes real Chromium and the opt-in desktop test.
The desktop test opens a temporary editor, clicks it, enters Unicode text,
saves using Ctrl+S, and reads the actual file through the agent loop. Model
responses are scripted. Image REST payloads are checked with mocked HTTP.
Live Gemini completed the Notepad save/readback workflow in the user's run
`20261024T051708Z-30a1d075`. An earlier run hit a rate limit before saving.
Its screenshot sequence also showed partial text
rendering immediately after typing. Input is now paced per character and the
skill re-observes before deciding to retype.

Normal tests never control the desktop. To explicitly run the real editor test:

```bash
RUN_DESKTOP_TESTS=1 python -m unittest discover -s tests -v
```

References: Google, [Gemini image inputs](https://ai.google.dev/gemini-api/docs/image-understanding);
PyAutoGUI, [desktop controls and fail-safe](https://pyautogui.readthedocs.io/en/latest/);
Microsoft, [SendInput](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput).

## Durable runs and human handoff

New live runs save `config.json` and an atomic `checkpoint.json` beside their
event log. Checkpoints contain the original task, skill snapshot, completed
tool records, pending action/question, written-file tracking, and cumulative
request/token/image counters. API keys and model private thoughts are not saved.
Tool contents and human answers are saved, just as in the event log.

The default `ask_user` still asks in the active terminal. To save the question
and exit instead:

```bash
python main.py run 'Ask me which filename to use before creating a file containing exactly: Handoff works. Read it back to verify.' --detach-on-handoff
```

Use the printed run ID in these commands:

```bash
python main.py status RUN_ID
python main.py resume RUN_ID --answer 'Use handoff_test.txt.'
```

`status` shows the pending question and counters. A missing terminal input stream
also leaves a durable pending question rather than losing the run. Resumed runs
keep the original skill and command configuration, even if their source files
changed. Answering is a CLI handoff channel; email/chat-service integrations are
not implemented. Ordinary answers are not action approval; protected browser
actions use the separate approval flow below.

After a provider error, wait out its cooldown, then resume the same run:

```bash
python main.py resume RUN_ID
```

Limits remain cumulative. If a local ceiling was reached, explicitly raise it:

```bash
python main.py resume RUN_ID --max-requests 50 --max-image-requests 50 --max-run-tokens 250000
```

If execution stopped during a tool action, its side effect may already have
occurred. Resume refuses to proceed without an operator note:

```bash
python main.py resume RUN_ID --note 'The file appears to exist. Read it before deciding whether any write is needed.'
```

Interrupted actions are not replayed automatically. A protected action that has
not executed can be explicitly approved and executed once by the harness. The model receives durable tool
history as context and chooses fresh observations/actions. It can still make
mistakes, so this is not an exactly-once guarantee for external UI actions.
Old evidence is invalidated; file hashes and current browser/desktop observations
must be checked again. A desktop emergency `STOP` file must be removed by the
operator after reviewing the interrupted run. Successful and cancelled runs cannot be resumed.

**Session limits:** desktop apps remain on the actual desktop, but the model must
observe again. The isolated browser closes on exit. Resuming creates a new context
using saved cookies, local storage and IndexedDB, then navigates to the last URL
and captures a fresh observation. This can preserve login when the application
supports it; expired or revoked sessions still require authentication. Session
storage, unsaved forms, JavaScript memory, additional tabs and the live page are
not restored. Use inline handoff when retaining the live page is necessary.
Run state is retained, not a complete browser or OS snapshot. Checkpoint recovery
does not preserve raw provider conversations/signatures across processes: it
starts a new model conversation from recorded facts and the original task.

Only runs created after this feature have resumable checkpoints. Older logs are
not automatically converted. Failed requests with no returned usage can consume
unreported provider tokens. Reported usage and attempted request counts are kept;
a new process does not restore the previous pacing timer.

Process locks prevent simultaneous resume of the same run. CLI browser/desktop
runs also share a computer lock so two workers cannot control the session at once.
Locks are released by the OS on process exit, including a crash.

## Saved browser sessions and action approval

Browser runs now save private `runs/RUN_ID/browser_session.json` after successful
browser tools, before approval, and on orderly close. It contains cookies, local
storage, IndexedDB and the last URL. Treat it as credential material. It is covered
by the existing `runs/` ignore rule and is excluded from automatic evidence exports.
Restoration uses only this run's data, never your personal browser profile. Saving
or restoring failures are explicit; the harness does not silently start signed out.
Earlier browser runs without this file require an explicit fresh session:

```bash
python main.py resume RUN_ID --fresh-browser --answer 'Your answer if a question is pending'
```

Omit `--answer` when no question is pending; uncertain interrupted tools still need
`--note`. `--fresh-browser` discards saved storage for this resume and cannot be
combined with approving a pending action. Restoring navigates to the saved URL;
it must be safe to reload. A URL whose GET request itself performs a transaction
is not safe to reopen automatically. No complete browser/OS snapshot is claimed.

Supply `--approval-policy PATH.json` to select browser actions requiring approval:

```json
{
  "rules": [
    {"tool": "browser_click", "match": {"role": "button", "name": "Confirm mock transaction"}}
  ]
}
```

Rules support `browser_open`, `browser_fill`, `browser_click`, `browser_scroll`,
`browser_select` and `browser_press`. Keyboard actions can submit forms; include
them in a policy when they can reach a protected effect.
`match` compares an exact subset of tool arguments; `{}` protects every call to
that tool. Invalid rules fail explicitly. The CLI snapshots the policy into run
configuration, including scheduled/event jobs, so changing its source file does
not change an existing run. No policy means no new approval interception.

Matching tool calls are intercepted in the harness before execution, regardless
of whether the model asks permission. The terminal shows the exact arguments,
current page text, URL and screenshot path. Approval is bound to a generated ID,
the exact action arguments and a hash of page structure and form values. Any
change to those observations invalidates approval, including a login redirect or
lost unsaved form values. This comparison is deliberately conservative; changing
page text or hidden form values can require a new approval even when the visible
transaction looks similar. A website can still change after the check: this does
not provide server-side transaction locking.

Inline handoff accepts only `approve APPROVAL_ID` or `reject APPROVAL_ID`. With
`--detach-on-handoff`, the run exits as `waiting_for_approval` and prints:

```bash
python main.py status RUN_ID
python main.py resume RUN_ID --approve APPROVAL_ID
# Or reject instead:
python main.py resume RUN_ID --reject APPROVAL_ID
```

`--answer yes` is not approval. Wrong IDs fail before model/browser startup.
Approval executes the saved action after fresh state checks, before the next
model request; the model must observe/verify its outcome rather than repeat it.
Approval is consumed before execution. If interrupted, inspect the outcome and
use `--note`; the same approval ID cannot execute it again. A rejection ends the
run as `cancelled`, without opening the browser or calling the model. There is no
automatic retry of an approved submission. Approval events, decisions and restored
observations appear in replay and exports. Recording remains segmented across
detached processes.

**Scope:** this is a gate for configured browser tool calls, not automatic payment
detection or a security sandbox. Another selector, navigation path, configured
command or desktop action may reach the same external effect without matching a
rule. Review policy coverage and available tools for each task; desktop/payment
integration and real booking validation are not part of this milestone. The mock
fixture demonstrates enforcement for its protected confirmation button.

### Try the combined local demo

From `Alum_Track`, activate the existing environment. In one Git Bash terminal:

```bash
source .venv/Scripts/activate
python -m http.server 8765 --bind 127.0.0.1 --directory browser_demo
```

If that server is already running with this directory, reuse it. In another terminal:

```bash
source .venv/Scripts/activate
source ~/.bash_profile
export GOOGLE_API_KEY
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python main.py run 'Open http://127.0.0.1:8765/transaction.html. Sign in as Demo User. Prepare 7 demo credits to Demo Recipient. Request confirmation through the normal tool, then verify the receipt and that exactly one transaction was confirmed.' --browser --skill mock_transaction --approval-policy browser_demo/approval_policy.json --detach-on-handoff --max-requests 30 --max-run-tokens 80000
```

Use the printed run/approval IDs to approve. The reopened browser should still
show Demo User, confirm the saved transaction and verify its receipt. Repeat the
initial command for a new isolated run and reject its approval instead; status
should become `cancelled` with no confirmed transaction. Append `--record-screen`
to capture the primary screen and every attempted tool step, or `--vision` to send
browser images to the model. Budgets above are configurable ceilings, not usage
predictions. The fixture uses local mock cookies/storage and demo credits only.

For an automated check with no API key or model quota (real headless Chromium,
scripted model replies, temporary run files):

```bash
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python -m unittest discover -s tests -p test_approval.py -v
```

These tests cover inline/detached approval, preserved mock login, rejection,
wrong/stale approval, interruption after submission, image evidence on resume,
and private-session exclusion from export. Actual website session behavior and
live model task success still need separate validation.

Implementation references: Microsoft Playwright,
[authentication/storage state](https://playwright.dev/python/docs/auth) and
[BrowserContext.storage_state](https://playwright.dev/python/docs/api/class-browsercontext#browser-context-storage-state).

## Schedule and event triggers

Queue a one-shot task with a **future** timestamp and explicit UTC offset.
Replace the placeholder below; `+05:30` is the user's local offset:

```bash
python main.py schedule 'Check the Python version and verify it.' --at 'YYYY-MM-DDTHH:MM:SS+05:30'
python main.py worker
```

The schedule/on-event commands accept the same task, skill, browser/desktop,
and budget options as `run`. They snapshot skill text and command configuration,
but do not snapshot workspace files. Enqueueing does not call the model.
The worker reads API credentials from its own environment; source your profile
and activate the same virtual environment before starting it.

Keep the worker terminal running and the computer awake. Desktop jobs also need
an unlocked session. This is a foreground worker, not a Windows service; it does
not wake the computer or restart itself after reboot. It polls every second and
runs one job at a time. A job more than 60 seconds late is explicitly marked
`missed`; configure `--max-lateness` when enqueueing if a different tolerance is
appropriate. Scheduling starts the agent run, not a guaranteed exact-time UI click.

File events provide a simple generic adapter boundary. Choose a marker that does
not exist yet:

```bash
python main.py on-event 'Check the Python version and verify it.' --event-file workspace/start_check.ready
python main.py worker
```

From another Git Bash terminal in `Alum_Track`, create the marker:

```bash
touch workspace/start_check.ready
```

The job fires once when the marker appears. Marker contents are ignored; they
cannot replace the queued task. The worker does not delete the marker. Register
another job with a new marker for another event. This is not yet an email listener
or webhook; an external adapter could create the marker later.

```bash
python main.py jobs
python main.py worker --once
```

`jobs` shows dispatch status and run IDs. `worker --once` checks currently ready
jobs and exits. The worker claims a job durably before execution and never retries
running, failed, interrupted, or waiting jobs automatically. After a crash, a job
may still say `running`; inspect its run with `status` and explicitly `resume` it.
If the process died before creating a run checkpoint, inspect the job/run files
before deliberately enqueueing a replacement. A job record describes its original
dispatch; after manual resume, `status RUN_ID` is authoritative for run status.
Queued jobs force detached handoff so a pending question does not block the worker.

Local tests cover process-independent handoff, provider failure recovery, uncertain
write handling, fresh evidence, locks, timezone validation, missed schedules,
one-shot dispatch, and an event-to-agent CLI path. Model replies are scripted;
the user has also validated scheduled and ordinary CLI handoff workflows live.
Browser approval/session tests use a scripted provider against local Chromium.

## Tools and verification

| Tool | Behavior |
| --- | --- |
| `list_files` | Lists one directory within the workspace. |
| `read_file` | Returns a complete UTF-8 file and its SHA-256. |
| `write_file` | Creates a file; replacing an existing file requires `overwrite=true`. |
| `run_command` | Executes a named, fixed command from the configured allowlist. |
| `ask_user` | Pauses for terminal input and continues in the same process. |
| `report_blocker` | Ends as blocked with observed evidence, without claiming success. |
| `write_extracted_file` | Browser runs: writes a numbered list from rechecked extraction evidence; no arbitrary content. |
| `finish` | Requires successful observation step IDs and checks file evidence. |

Every action requires a brief `reason`. Commands run with `shell=False`; the model
cannot supply arbitrary shell text or change command arguments. The only default
command is `python_version`, which invokes the current Python executable with
`--version`. To add trusted commands, supply `--commands commands.json`, for example:

```json
{
  "git_version": ["git", "--version"]
}
```

An explicit command file replaces the default list. Only configure commands you
have reviewed. Commands run as your OS user and are **not an OS sandbox**: their
scripts can access files outside the workspace and inherit the process environment.
The workspace restriction applies to the direct file tools. Configure executable
paths rather than `.bat` or `.cmd` files. Command timeouts terminate the direct
process; they do not guarantee termination of child processes it launches.

`finish` accepts evidence from successful `read_file` and `run_command` actions.
Each file written through the file tool must be included in readback evidence.
The harness rechecks file hashes at completion to reject stale observations.
Command output must be successful and untruncated. These checks establish observed
artifacts and command outcomes; they do **not** prove that a natural-language task
was correctly understood or that a summary is accurate. Review demo outputs and
add task-specific acceptance checks as we expand the project.

## Limits and failure behavior

See [RELIABILITY.md](RELIABILITY.md) for the controlled failure matrix, the live
flight-run diagnosis, and limitations. Run the local recovery checks without any
model API requests:

```bash
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python -m unittest discover -s tests -p test_recovery.py -v
```

The harness retains only the latest full browser snapshot in model request history;
older snapshots remain in the JSONL log and durable checkpoint, with omission notes
in model context and `context_compacted` events. Tool arguments, errors, URLs,
verification text and provider signatures are preserved. Resume context omits old
browser snapshots and supplies fresh restored observations. This limits repeated
page text; it does not guarantee a token budget or model correctness.

Within one process, after the same browser action/verification arguments fail twice
without a successful corrective browser action, another identical attempt is
stopped before execution. Clock text or a new browser_observe screenshot does not
reset the check. Two invalid finish attempts also require new successful
verification or correction before another finish; changing evidence IDs alone
does not help. Successful browser mutations clear the failure history. The stop is
logged as `recovery_stop` with `repeated_browser_failure`, and `pending` is empty
because the blocked attempt did not run. Explicit resume starts a fresh check;
inspect the cause first. This is not a detector for successful but irrelevant
clicks or every kind of loop.

Provider failures and budget stops now include structured `failure` details in
result/checkpoint and `status` output. Rate-limit errors preserve the reported
Retry-After value and an explicit recovery hint. There is no automatic retry,
waiting, model substitution or provider switch. Counters reflect model requests
actually started; a request blocked by the image budget is not counted as sent.

Current defaults (our configuration, not provider quotas):

- No model-request, tool-action or image-request count ceiling. Their respective
  `--max-requests`, `--max-steps` and `--max-image-requests` options accept a positive
  finite ceiling, or `0` / `unlimited` to disable it. Saved runs retain saved limits
  unless explicitly overridden on resume.
- No total run token limit. Usage is still counted and logged. Set
  `--max-run-tokens NUMBER` for a finite limit, or `0` / `unlimited` to remove it.
- 2,048 maximum output tokens per request; 45-second HTTP timeout.
- Live CLI/UI requests start at least 0.5 seconds apart. Override with
  `--min-request-interval SECONDS`; 0 disables pacing. Waits are announced and
  logged, and desktop emergency-stop checks continue during them.
- 15-second command timeout.
- 64 KiB per file; 200 entries per directory listing.
- 16 KiB returned for each command output stream. Truncation is explicitly flagged.

An explicitly configured finite token budget is an **observed usage stop**, not a strict billing or quota cap:
the response that crosses it has already consumed tokens, but its actions are not
executed. Failed requests may also consume provider quota without reporting usage.
The loop stops if token usage is missing, a response is incomplete, limits are
reached, or the provider fails. There is no automatic retry, model substitution,
provider switch, or offline fallback. A quota error includes the HTTP status and
Retry-After value when supplied. Tool failures are returned to the model as explicit
errors, so it can correct its next action within the run limits.

Request pacing is local to one run. It does not track previous runs or other
clients using the same Google project, and it does not prevent token-per-minute
or daily quota failures. The user's 2026-10-24 response reported a free-tier
limit of 15 requests/minute for their project/model. That is account evidence,
not a universal quota. See Google's rate-limit reference below. After a 429,
wait for the provider's reported cooldown before starting a new run. There is
still no automatic retry. Use `resume RUN_ID` for new checkpointed runs, inspecting
uncertain actions instead of blindly repeating side effects.

For longer desktop trials, configure all relevant local limits, for example
`--max-requests 30 --max-image-requests 30 --max-run-tokens 150000`.
These are explicit ceilings, not predicted usage or guarantees of completion.

Command output is decoded as UTF-8. Undecodable bytes appear as literal `\xNN`
escapes; they are not discarded. File reads require valid UTF-8 and fail otherwise.
User input pauses are not timed out. File/command data, the task, and answers are
sent to the selected API in live mode. Logs contain tool arguments, file content,
command output, and user answers: use non-sensitive fixtures during development.
API credentials are not written to logs by the provider adapter. Private model
thought content is not logged; opaque provider metadata is retained in memory for
the next API turn.

## Implementation map

- `tools.py`: tool declarations, argument validation, workspace file operations,
  and configured commands.
- `gemini.py`: REST request/response handling and explicit provider errors.
- `harness.py`: sequential agent loop, run limits, state events, and verification.
- `main.py`: CLI, Markdown skill loading, and explicitly scripted offline demo.
- `web_ui.py` / `ui.html` / `assets/logo.svg`: local task console, environment readiness and supplied branding.
- `browser.py`: optional isolated browser session, observations, actions, screenshots, and text checks.
- `desktop.py`: opt-in Windows input, screenshot coordinates, focus checks, and emergency stop.
- `vision.py`: bounded inline image attachments and image-history retention.
- `state.py`: atomic JSON snapshots and process-lifetime locks.
- `jobs.py`: one-shot schedule/file-event jobs and the foreground worker.
- `approval.py`: operator policy validation, exact-action binding and detached rejection.
- `recording.py`: optional Windows screen video and per-step evidence screenshots.
- `replay.py` / `replay.html`: offline viewer and portable exports with hash manifests.
- `browser_demo/`: local form fixture served with Python's HTTP server.
- `skills/`: reusable task instructions selected by name.
- `tests/test_agent.py`: tools, failure boundaries, loop behavior, and mocked HTTP.

## Problem-statement review

Source: [Do You Know How to Train?](../Hackathon%20PS/Do%20You%20Know%20How%20to%20Train_.pdf),
Syntax Error 2026, especially "Every harness must have", "What To Submit", and
"Terms and Conditions". Last milestone review: 2026-10-24.

Review the source at the start/end of each milestone, after significant scope
changes, and before choosing the next phase. `AGENTS.md` preserves this instruction
for future work. This is a development checkpoint, not a background scheduled job.

| PS requirement | Current status |
| --- | --- |
| Generic harness and task skills | Implemented; file/terminal/browser skills validated live. The loopback task console is locally checked for UI behavior and key inheritance; a live model task through its polished interface remains unvalidated. |
| Shell, files, browser | Implemented baseline; shell uses configured fixed commands. |
| Screenshots plus structure | Implemented; live visual Notepad task passed. |
| Desktop mouse and keyboard | Windows primary-monitor baseline; live Notepad save/readback passed. |
| Plan/act/observe/verify loop | Implemented; visual judgment distinguished from file/browser assertions. |
| Task adherence and extraction evidence | General per-item extraction and source/count constraints implemented and locally tested; live YouTube empty-feed blocker validated. Successful populated-site extraction and full semantic task validation remain. See RELIABILITY.md. |
| Error recovery rehearsal | Local mocked-provider and real-Chromium scenarios implemented; see RELIABILITY.md. Live arbitrary-site reliability remains unproven. |
| Chat, schedule, event triggers | CLI task input, one-shot schedules and file-event triggers implemented; scheduled run validated live by user; dedicated chat/email connectors remain. |
| Human handoff and resume | Live UI question/approval controls retain the browser process; local HTTP and Chromium approval tests passed. CLI detached restore remains available; scheduled jobs still detach. Live model validation of the new UI controls and external chat/payment integration remain. |
| Screenshot and reason for every step; replay | Offline viewer implemented; every attempted tool step gets a primary-screen image when recording is enabled and capture succeeds. Older/missing evidence is flagged. |
| Booking evidence and recordings | Whole-process screen recording and portable export implemented and locally tested; detached gaps are not recorded. Ticket/PNR, external phone video and Drive submission remain. |
| Qualifying scheduled IRCTC task | Deferred at user's request; remains a qualification requirement. |
| Self-improving/demo-generated skills | Bonus; not implemented. |

## Next milestones

1. Validate recovery behavior with live model tasks; controlled local assessment is documented in RELIABILITY.md.
2. Validate broader general tasks using skills across browser, desktop, terminal and files.
3. Implement dedicated chat/approval integrations as needed, and rehearse recording/export.
4. Add and rehearse the qualifying booking skill when the user resumes that scope.

A second provider and automatic retry are not implemented. Failed runs keep
their files and logs for inspection; they are not automatically rolled back.

## API references

- ImageIO, [imageio-ffmpeg package and executable selection](https://github.com/imageio/imageio-ffmpeg).
- Google, [GenerateContent REST API](https://ai.google.dev/api/generate-content).
- Google, [Function calling](https://ai.google.dev/gemini-api/docs/function-calling).
- Google, [Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite).
- Google, [Rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).
