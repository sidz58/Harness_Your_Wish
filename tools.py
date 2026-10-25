"""Small, explicit tools for the first file/terminal milestone."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile


MAX_FILE_BYTES = 64 * 1024
MAX_OUTPUT_BYTES = 16 * 1024
MAX_ENTRIES = 200


def declaration(name, description, properties, required):
    properties = {**properties, "reason": {"type": "string", "description": "Brief purpose of this action."}}
    return {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": [*required, "reason"],
    }}


STRING = {"type": "string"}
DECLARATIONS = [
    declaration("list_files", "List one workspace directory, including hidden entries; no recursion.",
                {"path": STRING}, ["path"]),
    declaration("read_file", "Read a complete UTF-8 file and its SHA-256. Files larger than 64 KiB fail.",
                {"path": STRING}, ["path"]),
    declaration("write_file", "Write a UTF-8 file. Parent directories must exist. Explicit overwrite is required for an existing file.",
                {"path": STRING, "content": STRING, "overwrite": {"type": "boolean"}}, ["path", "content"]),
    declaration("run_command", "Execute a configured command by name, with fixed arguments and a timeout. No arbitrary shell code.",
                {"command": STRING}, ["command"]),
    declaration("ask_user", "Pause the terminal session to ask for missing information.",
                {"question": STRING}, ["question"]),
    declaration("report_blocker", "End as blocked, not succeeded, when the requested information/task cannot be completed. Explain what is missing and cite actual observation steps. Do not silently substitute another task or fabricate results.",
                {"message": STRING, "evidence_steps": {"type": "array", "items": {"type": "integer"}}}, ["message", "evidence_steps"]),
    declaration("finish", "Complete the task using successful read_file/run_command action IDs as evidence. Re-read every file written before finishing.",
                {"summary": STRING, "evidence_steps": {"type": "array", "items": {"type": "integer"}}},
                ["summary", "evidence_steps"]),
]


def validate_call(name, arguments, declarations=None):
    schema = next((d["parameters"] for d in (DECLARATIONS if declarations is None else declarations) if d["name"] == name), None)
    if schema is None:
        raise ValueError(f"Unknown tool: {name}")
    if not isinstance(arguments, dict):
        raise ValueError("Tool arguments must be an object")
    missing = set(schema["required"]) - arguments.keys()
    extra = arguments.keys() - schema["properties"].keys()
    if missing or extra:
        raise ValueError(f"Invalid arguments: missing={sorted(missing)}, unknown={sorted(extra)}")
    types = {"string": str, "boolean": bool, "array": list, "integer": int}
    for key, value in arguments.items():
        expected = schema["properties"][key]["type"]
        if type(value) is not types[expected]:
            raise ValueError(f"{key} must be {expected}")
        if expected == "array":
            item_type = schema["properties"][key]["items"]["type"]
            if any(type(item) is not types[item_type] for item in value):
                raise ValueError(f"{key} must contain {item_type} values")
    for key in ("reason", "path", "command", "question", "summary"):
        if key in arguments and not arguments[key].strip():
            raise ValueError(f"{key} cannot be blank")


class Toolbox:
    def __init__(self, workspace, commands=None, command_timeout=15):
        self.workspace = Path(workspace).resolve(strict=True)
        if not self.workspace.is_dir():
            raise ValueError("Workspace must be an existing directory")
        self.commands = {"python_version": [sys.executable, "--version"]} if commands is None else commands
        if not isinstance(self.commands, dict):
            raise ValueError("Commands must be an object mapping names to argument lists")
        for name, argv in self.commands.items():
            if not isinstance(name, str) or not name.strip() or not isinstance(argv, list) or not argv:
                raise ValueError("Each configured command needs a name and a non-empty argument list")
            if any(not isinstance(arg, str) or "\0" in arg for arg in argv) or not argv[0]:
                raise ValueError(f"Invalid argument list for command {name}")
        if command_timeout <= 0:
            raise ValueError("Command timeout must be positive")
        self.command_timeout = command_timeout
        self.written = set()

    def resolve(self, path):
        raw = Path(path)
        if raw.anchor or ":" in path:
            raise ValueError("Use a workspace-relative path without a drive or alternate data stream")
        resolved = (self.workspace / raw).resolve()
        if not resolved.is_relative_to(self.workspace):
            raise ValueError("Path leaves the workspace (including through a symbolic link)")
        return resolved

    def relative(self, path):
        return path.relative_to(self.workspace).as_posix()

    def list_files(self, path):
        directory = self.resolve(path)
        entries = []
        for entry in directory.iterdir():
            if len(entries) >= MAX_ENTRIES:
                raise ValueError(f"Directory exceeds {MAX_ENTRIES} entries; choose a smaller directory")
            entries.append({"name": entry.name, "kind": "link" if entry.is_symlink()
                            else "directory" if entry.is_dir() else "file"})
        return {"path": self.relative(directory), "entries": sorted(entries, key=lambda e: e["name"])}

    def read_file(self, path):
        target = self.resolve(path)
        with target.open("rb") as source:
            data = source.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"File exceeds {MAX_FILE_BYTES} bytes; no partial content was returned")
        return {"path": self.relative(target), "content": data.decode("utf-8"),
                "sha256": hashlib.sha256(data).hexdigest()}

    def write_file(self, path, content, overwrite=False):
        target = self.resolve(path)
        data = content.encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"Content exceeds {MAX_FILE_BYTES} bytes")
        if overwrite:
            # Replace atomically so a failed write cannot truncate an existing file.
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
                temporary_path = Path(temporary.name)
                try:
                    temporary.write(data)
                except BaseException:
                    temporary.close()
                    temporary_path.unlink()
                    raise
            try:
                os.replace(temporary_path, target)
            finally:
                if temporary_path.exists():
                    temporary_path.unlink()
        else:
            with target.open("xb") as destination:
                destination.write(data)
        self.written.add(self.relative(target))
        return {"path": self.relative(target), "bytes_written": len(data),
                "sha256": hashlib.sha256(data).hexdigest()}

    def run_command(self, command):
        if command not in self.commands:
            raise ValueError(f"Command not configured: {command}. Available: {sorted(self.commands)}")
        argv = self.commands[command]
        if Path(argv[0]).suffix.lower() in {".cmd", ".bat"}:
            raise ValueError("Batch files are not supported; configure an executable directly")
        # Disk capture avoids retaining arbitrarily large command output in RAM.
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            completed = subprocess.run(argv, cwd=self.workspace, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, timeout=self.command_timeout,
                                       shell=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            result = {"command": command, "returncode": completed.returncode}
            for name, stream in (("stdout", stdout), ("stderr", stderr)):
                stream.seek(0)
                data = stream.read(MAX_OUTPUT_BYTES + 1)
                result[name] = data[:MAX_OUTPUT_BYTES].decode("utf-8", errors="backslashreplace")
                result[f"{name}_truncated"] = len(data) > MAX_OUTPUT_BYTES
        result["ok"] = completed.returncode == 0
        if not result["ok"]:
            result["error"] = f"Command exited with status {completed.returncode}"
        return result

    def execute(self, name, arguments):
        validate_call(name, arguments)
        if name not in {"list_files", "read_file", "write_file", "run_command"}:
            raise ValueError(f"Tool {name} is handled by the agent loop")
        kwargs = {key: value for key, value in arguments.items() if key != "reason"}
        try:
            return {"ok": True, **getattr(self, name)(**kwargs)}
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            return {"ok": False, "error": str(error), "error_type": type(error).__name__}
