# Summarize notes

Use this skill to turn local text notes into a concise Markdown summary.

## Inputs

The task must identify the source file or files and the destination file.
Ask the user for any missing paths. Paths are relative to the workspace.

## Procedure

1. Read every source file in full. If a file is missing or unreadable, report the
   specific problem and ask for a correction; do not invent its contents.
2. Summarize only facts supported by the source text. Preserve important names,
   numbers, decisions, and uncertainties. Distinguish explicit action items from
   your own suggestions, and include suggestions only when requested.
3. Write a short Markdown document with a source-file list and a summary. Include
   decisions and next steps only if the source contains them. Do not replace the
   source files. If the destination exists, inspect it and ask before replacing
   it unless the user has already authorized replacement.
4. Read the saved destination. Compare it with the source observations to check
   for omissions, invented facts, and incorrect numbers. Correct any problems
   and read back the corrected file.
5. Finish with the source and final destination read steps as evidence. State
   where the summary was saved.

## Completion

The saved summary exists, was read back, and accurately reflects the supplied
notes. A successful write alone is not enough to finish.
