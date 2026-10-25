# Runtime report

Use this skill to record the observed Python runtime in a local Markdown report.

## Inputs

The task must give a destination filename. Ask the user if it is missing.

## Procedure

1. Run the configured `python_version` command. Use its actual output; do not
   infer the version from memory or from the environment description.
2. If the command fails, explain the error and ask for help. Do not write a
   report claiming a successful runtime check.
3. Write a Markdown report with a title and the observed Python version. Include
   only runtime details returned by the command. If the destination exists,
   inspect it and ask before replacing it unless replacement is already authorized.
4. Read back the report and confirm that its version matches the command output.
5. Finish with both the command step and the final report read step as evidence.
   Mention the saved report's path.
