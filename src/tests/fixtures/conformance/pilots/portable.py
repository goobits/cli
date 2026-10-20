"""Portable equivalents of the Rust and TypeScript pilots' parser contracts."""

import json
import os
import sys
import uuid
from pathlib import Path

language, *args = sys.argv[1:]
eager = next((i for i, arg in enumerate(args) if arg in {"--help", "--version"}), None)
prefix = args if eager is None else args[:eager]
words = [arg for arg in prefix if not arg.startswith("--")]
command = "pilot"
if words and words[0] == "item":
    command += " item" + (" " + words[1] if len(words) > 1 else "")
machine = "--json" in (prefix if language == "rust" else args)
usage = (
    "Usage: "
    + command
    + (" INPUT" if command.endswith("require") else "")
    + " [OPTIONS]"
)
help_text = usage + "\n" + Path(os.environ["PILOT_HELP"]).read_text()
code = 0
if eager is not None:
    version = args[eager] == "--version"
    text = "2.0.0" if version else help_text
    if not machine:
        print(text)
        sys.exit(0)
    data = {"version" if version else "text": text}
else:
    allowed = {
        "--json",
        "--quiet",
        "--verbose",
        "--yes",
        "--no-input",
        "--canonical-exits",
    }
    if (
        any(arg.startswith("--") and arg not in allowed for arg in args)
        or {"--quiet", "--verbose"}.issubset(args)
        or (command.endswith("require") and "INPUT" not in args)
    ):
        code = 2 if "--canonical-exits" in args else (1 if language == "legacy" else 22)
    if "--verbose" in args:
        print("native diagnostic", file=sys.stderr)
    data = None if code else {"schema": "pilot.payload/2", "value": "value"}
result = {
    "contract": "v2",
    "path": command,
    "success": code == 0,
    "payload": data,
    "problems": []
    if not code
    else [
        {
            "code": "usage",
            "message": "bad input",
            "retryable": False,
            "next_action": "Read --help",
            "target": None,
        }
    ],
    "correlation": str(uuid.uuid4()),
    "state": "failed" if code else "done",
}
if not code and eager is None:
    (Path(os.environ["GOOBITS_CONFORMANCE_STATE"]) / "native-result.json").write_text(
        json.dumps(result)
    )
print(json.dumps(result))
sys.exit(code)
