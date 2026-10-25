# Write and verify a desktop note

Use Windows desktop tools and screenshots to create a note in Notepad.

## Inputs

The task must supply the exact text and a new workspace-relative destination.
Ask for missing inputs. Inspect the workspace first. If the destination already
exists, ask for a different name unless overwriting it was explicitly authorized.

## Procedure

1. Observe the desktop. Launch Notepad with Windows+R, type `notepad`, and press
   Enter. Observe again if it has not finished opening. Use a new blank document;
   do not modify an existing user document or recover/close their existing tabs.
2. Use the screenshot to locate and focus the blank editor. Type the supplied
   text literally using desktop_type. Inspect the returned screenshot. If it
   appears partially rendered, observe again before deciding to clear/retype.
3. Save with Ctrl+Shift+S or Ctrl+S as appropriate to the observed app state.
   Inspect the dialog before typing. Focus the File name field (Alt+N in the
   standard Windows Save As dialog), select its existing value, and enter the
   full absolute destination including the filename. This avoids navigating
   folders through the address bar. Use the workspace supplied by the harness.
   Choose UTF-8 if an encoding is requested.
4. Inspect the post-save screenshot. If a dialog remains, resolve it only within
   the user's authorization. Never blindly accept an overwrite prompt.
5. Read the destination with read_file. Compare its entire contents with the
   requested text, including punctuation and whitespace. Fix through the editor
   and read again if necessary; do not replace this GUI task with write_file.
6. Observe the desktop, then record a desktop_verify finding supported by the
   screenshot. Finish citing both the read_file and desktop_verify steps.

## Failure handling

Use fresh observations after errors or focus changes. Ask for help if blocked.
An emergency stop ends the run; do not attempt to work around it.
