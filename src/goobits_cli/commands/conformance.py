"""CLI adapter for the subprocess conformance suite."""

import json
import sys
import uuid
from pathlib import Path
from typing import List, Optional

import typer

from ..__version__ import __version__
from ..conformance.suite import check_manifest

HELP = """Usage: goobits conformance check --manifest PATH [--json]
Arguments: none. Options: --manifest PATH (required; no default).
Shared flags before or after the command: --json --quiet --verbose --yes --no-input.
Examples: goobits conformance check --manifest tool.conformance.json --json
Side effects: runs the declared executable and isolated fixture subprocesses.
Configuration precedence: command flags only; no project/config options are supported.
Exit codes: 0 completed, 1 unhandled crash, 2 usage/input, 3 conformance failed, 4 blocked,
5 runtime, 124 deadline, 130 interrupted. Usage takes precedence over execution.
Schema: goobits.conformance.check/1 payload; Goobits envelope schema_version 1.
Identity mapping: docs/cli-standard.md#interaction-and-output (all envelope/error fields).
Simultaneous failures: retain every check; any failed check selects exit 3.
"""


def run_cli(argv: List[str]) -> int:
    """Parse locally so all parser failures also obey the machine contract."""
    request_id = str(uuid.uuid4())
    machine = "--json" in argv
    data = None
    errors = []
    code = 0
    words = [
        a
        for a in argv
        if a not in {"--json", "--quiet", "--verbose", "--yes", "--no-input"}
    ]
    command = "goobits"
    for part in ("conformance", "check"):
        if not words or words.pop(0) != part:
            break
        command += " " + part
    try:
        if "--help" in argv or "--version" in argv:
            # Native eager rule: first eager flag wins; JSON is recognized globally.
            eager = next(a for a in argv if a in {"--help", "--version"})
            prefix = argv[: argv.index(eager)]
            command = "goobits"
            if "conformance" in prefix:
                command += " conformance"
                if "check" in prefix:
                    command += " check"
            data = {"text": HELP} if eager == "--help" else {"version": __version__}
        else:
            if "--quiet" in argv and "--verbose" in argv:
                raise ValueError("--quiet and --verbose conflict")
            args = [
                a
                for a in argv
                if a not in {"--json", "--quiet", "--verbose", "--yes", "--no-input"}
            ]
            if args[:2] == ["conformance", "check"]:
                args = args[2:]
            if len(args) != 2 or args[0] != "--manifest":
                raise ValueError("Expected conformance check --manifest PATH")
            checks = check_manifest(Path(args[1]))
            data = {"schema": "goobits.conformance.check/1", "checks": checks}
            for check in checks:
                if check.get("warning"):
                    print(check["detail"], file=sys.stderr)
            if any(check["passed"] is False for check in checks):
                code = 3
                errors = [
                    {
                        "code": "conformance_failed",
                        "message": "CLI conformance checks failed",
                        "retryable": False,
                        "next_action": "Apply the failed checks' fix hints and rerun",
                        "target": args[1],
                    }
                ]
    except (ValueError, KeyError, TypeError, AttributeError, OSError) as exc:
        code = 2
        errors = [
            {
                "code": "invalid_manifest",
                "message": str(exc),
                "retryable": False,
                "next_action": "Provide a readable version 1 conformance manifest; see docs/cli-standard.md#conformance-interface",
                "target": None,
            }
        ]
    except KeyboardInterrupt:
        code = 130
        errors = [
            {
                "code": "interrupted",
                "message": "Conformance interrupted",
                "retryable": False,
                "next_action": "Inspect fixture state before rerunning",
                "target": None,
            }
        ]
    receipt = {
        "schema_version": 1,
        "command": command,
        "ok": not errors,
        "data": data,
        "errors": errors,
        "request_id": request_id,
        "status": "failed" if errors else "completed",
    }
    if machine:
        print(json.dumps(receipt, ensure_ascii=False))
    elif data and ("text" in data or "version" in data):
        print(data.get("text", data.get("version")))
    else:
        for check in (data or {}).get("checks", []):
            print(
                "{} {} ({}) {}".format(
                    "SKIP"
                    if check.get("skipped")
                    else "WARN"
                    if check.get("warning")
                    else "PASS"
                    if check["passed"]
                    else "FAIL",
                    check["rule"],
                    check["section"],
                    check["detail"],
                )
            )
            if check["passed"] is False:
                print("  Fix: " + check["fix_hint"])
        for error in errors:
            print(error["message"], file=sys.stderr)
    if "--verbose" in argv and "--quiet" not in argv:
        print("Conformance receipt " + request_id, file=sys.stderr)
    return code


conformance_app = typer.Typer(
    add_help_option=False,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)


@conformance_app.callback(
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def conformance(ctx: typer.Context) -> None:
    """Check a tool against docs/cli-standard.md."""
    raise typer.Exit(run_cli(["conformance"] + ctx.args))


class GoobitsApp(typer.Typer):
    """Dispatch conformance before native eager parsing to preserve its JSON errors."""

    def __call__(self, *args, **kwargs):
        argv = kwargs.get("args")
        if argv is None:
            argv = sys.argv[1:]
        # Existing commands retain their native parser and lifecycle.
        words = [
            a
            for a in argv
            if a
            not in {
                "--json",
                "--quiet",
                "--verbose",
                "--yes",
                "--no-input",
                "--help",
                "--version",
            }
        ]
        if words and words[0] == "conformance":
            raise SystemExit(run_cli(list(argv)))
        return super().__call__(*args, **kwargs)


def generated_check(manifest: Optional[str] = None, **kwargs) -> None:
    argv = ["conformance", "check"]
    if manifest:
        argv += ["--manifest", manifest]
    argv += [
        "--" + key.replace("_", "-")
        for key, value in kwargs.items()
        if value is True and key in {"json", "quiet", "verbose", "yes", "no_input"}
    ]
    raise SystemExit(run_cli(argv))
