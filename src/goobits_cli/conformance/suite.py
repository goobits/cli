"""Manifest-driven, isolated subprocess assertions. Never imports target code."""

import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

SECTIONS = {
    "commands": "commands-and-flags",
    "output": "interaction-and-output",
    "exits": "exit-codes",
    "work": "work-retries-and-versions",
    "manifest": "conformance-interface",
}
# Scenarios cannot silently disappear from a manifest. Inapplicability needs a reason.
SCENARIOS = {
    "read",
    "missing-input",
    "invalid-input",
    "invalid-flag",
    "conflict",
    "confirmation",
    "owner-decision",
    "denial",
    "unavailable",
    "verification",
    "timeout",
    "interrupt",
    "partial-failure",
    "multiple-errors",
    "acceptance",
    "completion",
    "stream",
    "stream-failure",
    "mutation",
    "lost-response",
    "unknown-fields",
    "unknown-version",
    "expiry",
}
CODES = {
    "missing-input": 2,
    "invalid-input": 2,
    "invalid-flag": 2,
    "conflict": 2,
    "confirmation": 4,
    "owner-decision": 4,
    "denial": 4,
    "unavailable": 5,
    "verification": 3,
    "timeout": 124,
    "interrupt": 130,
    "unknown-version": 2,
}
SHARED = ("--json", "--quiet", "--verbose", "--yes", "--no-input")


def envelope_errors(doc: Any, stream: bool = False) -> list:
    """Return type/semantic violations, allowing unknown optional fields."""
    if not isinstance(doc, dict):
        return ["envelope must be an object"]
    errors = []
    types = {
        "schema_version": int,
        "command": str,
        "ok": bool,
        "errors": list,
        "request_id": str,
        "status": str,
    }
    for key, kind in types.items():
        if key not in doc or type(doc[key]) is not kind:
            errors.append(key + " has wrong or missing type")
    if "data" not in doc:
        errors.append("data is missing")
    if errors:
        return errors
    if doc["schema_version"] != 1:
        errors.append("unsupported schema_version")
    if not doc["request_id"].strip() or not doc["command"].strip():
        errors.append("empty request_id or command")
    statuses = {"accepted", "completed", "failed"} | ({"running"} if stream else set())
    if doc["status"] not in statuses:
        errors.append("invalid status")
    if doc["ok"] != (not doc["errors"]) or doc["ok"] != (doc["status"] != "failed"):
        errors.append("ok/errors/status disagree")
    for error in doc["errors"]:
        if not isinstance(error, dict):
            errors.append("error must be an object")
            continue
        for key, kind in {
            "code": str,
            "message": str,
            "retryable": bool,
            "next_action": str,
        }.items():
            if type(error.get(key)) is not kind:
                errors.append("error." + key + " has wrong or missing type")
        for key in ("code", "next_action"):
            if not error.get(key):
                errors.append("error." + key + " is empty")
        if "target" not in error or (
            error["target"] is not None and not isinstance(error["target"], str)
        ):
            errors.append("error.target must be string or null")
    return errors


def documents(stdout: str, stream: bool = False, mapping=None) -> list:
    if not stdout.endswith("\n") or "\x1b" in stdout:
        raise ValueError("stdout needs a final newline and no terminal controls")

    def reject_constant(value):
        raise ValueError("non-JSON number: " + value)

    decoder = json.JSONDecoder(parse_constant=reject_constant)
    if stream:
        docs = [decoder.decode(line) for line in stdout.splitlines()]
        if mapping:
            docs = [map_envelope(doc, mapping) for doc in docs]
        if not docs or docs[-1].get("status") not in {
            "completed",
            "failed",
            "accepted",
        }:
            raise ValueError("stream needs a terminal receipt")
        if any(d.get("status") != "running" for d in docs[:-1]):
            raise ValueError("only running records may precede the terminal receipt")
    else:
        doc, end = decoder.raw_decode(stdout.lstrip())
        assert stdout.lstrip()[end:] == "\n", (
            "exactly one JSON document followed by one newline is required"
        )
        docs = [map_envelope(doc, mapping) if mapping else doc]
    for doc in docs:
        problems = envelope_errors(doc, stream)
        if problems:
            raise ValueError("; ".join(problems))
    return docs


def map_envelope(doc: dict, mapping: dict) -> dict:
    """Translate documented existing namespaces without weakening canonical validation."""
    assert mapping["documentation"], "semantic mappings need documentation"
    result = {key: lookup(doc, path) for key, path in mapping["fields"].items()}
    assert str(result["schema_version"]) in mapping["versions"], (
        "unsupported mapped envelope version"
    )
    result["schema_version"] = 1
    result["status"] = mapping["statuses"][result["status"]]
    result["errors"] = [
        {key: lookup(error, path) for key, path in mapping["error_fields"].items()}
        for error in result["errors"]
    ]
    return result


class Suite:
    def __init__(self, manifest: dict, base: Path, state: str):
        self.manifest = manifest
        self.base = base
        self.results = []
        # Do not pass credentials or service configuration from the calling shell.
        self.env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "SYSTEMROOT", "LANG"}
        }
        self.env.update(
            {
                "HOME": state,
                "TMPDIR": state,
                "NO_COLOR": "1",
                "TERM": "dumb",
                "PYTHONDONTWRITEBYTECODE": "1",
                "GOOBITS_CONFORMANCE_STATE": state,
            }
        )
        self.env.update(manifest.get("fixture", {}).get("env", {}))

    def check(self, rule: str, section: str, action, hint: str) -> None:
        try:
            action()
            passed, detail = True, ""
        except (
            AssertionError,
            AttributeError,
            IndexError,
            ValueError,
            KeyError,
            TypeError,
            OSError,
            subprocess.SubprocessError,
        ) as exc:
            passed, detail = False, str(exc) or "assertion failed"
        self.results.append(
            {
                "rule": rule,
                "section": "docs/cli-standard.md#" + SECTIONS[section],
                "passed": passed,
                "detail": detail,
                "fix_hint": hint,
            }
        )

    def decode(self, stdout: str, stream: bool = False) -> list:
        return documents(stdout, stream, self.manifest.get("envelope_mapping"))

    def run(self, argv: list, hook: bool = False, request=None):
        prefix = (
            self.manifest["fixture"]["argv"] if hook else self.manifest["executable"]
        )
        return subprocess.run(
            prefix + argv,
            input=json.dumps(request) if hook else "",
            capture_output=True,
            encoding="utf-8",
            errors="strict",
            cwd=self.base,
            env=self.env,
            timeout=self.manifest.get("timeout_seconds", 5),
            check=False,
        )

    def terminal_run(self, argv: list, tty: str):
        """Exercise each half-TTY and explicit noninteractive flags on a full TTY."""
        import pty

        master, slave = pty.openpty()
        chunks = []

        def drain():
            try:
                while True:
                    chunk = os.read(master, 4096)
                    if not chunk:
                        break
                    chunks.append(chunk)
            except OSError:
                pass

        output_tty = tty in {"stdout", "both"}
        reader = threading.Thread(target=drain, daemon=True)
        try:
            process = subprocess.Popen(
                self.manifest["executable"] + argv,
                stdin=slave if tty in {"stdin", "both"} else subprocess.PIPE,
                stdout=slave if output_tty else subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.base,
                env=self.env,
            )
            os.close(slave)
            slave = -1
            if output_tty:
                reader.start()
            try:
                stdout, stderr = process.communicate(
                    timeout=self.manifest.get("timeout_seconds", 5)
                )
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
                raise
            if output_tty:
                reader.join(timeout=1)
                stdout = b"".join(chunks).replace(b"\r\n", b"\n")
            return subprocess.CompletedProcess(
                argv, process.returncode, stdout.decode("utf-8"), stderr.decode("utf-8")
            )
        finally:
            if slave != -1:
                os.close(slave)
            os.close(master)

    def fixture(self, action: str, scenario: str = "read") -> dict:
        result = self.run([], True, {"action": action, "scenario": scenario})
        assert result.returncode == 0, "fixture hook failed: " + result.stderr
        value = json.loads(result.stdout)
        assert isinstance(value, dict), "fixture hook must return an object"
        return value

    def validate_manifest(self):
        m = self.manifest
        assert type(m["manifest_version"]) is int and m["manifest_version"] == 1
        for argv in [m["executable"], m["fixture"]["argv"]]:
            assert (
                isinstance(argv, list)
                and argv
                and all(isinstance(a, str) for a in argv)
            )
        assert m["fixture"]["isolation"], "declare isolated backend/local state"
        assert m["payload_schema"]["identifier"] and m["payload_schema"]["version"]
        assert m["version"] and m["command_tree"]
        exceptions = m.get("entrypoint_exceptions", [])
        for command in m["command_tree"]:
            parts = command.split()
            assert parts[0] == m["name"] and (len(parts) >= 3 or command in exceptions)
            assert all(re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", p) for p in parts)
        for flag in m["long_flags"]:
            assert re.fullmatch(r"--[a-z][a-z0-9]*(?:-[a-z0-9]+)*", flag)
        covered_commands = {p["command"] for p in m["probes"].values()}
        covered_commands.update(
            p.get("inspection_command") for p in m["probes"].values()
        )
        assert set(m["command_tree"]) <= covered_commands, (
            "provide a safe probe for every canonical command"
        )
        if "confirmation" in m["probes"]:
            assert "confirmation-yes" in m["probes"], (
                "prove --yes supplies confirmation"
            )
        for scenario in SCENARIOS:
            assert scenario in m["probes"] or m["inapplicable"].get(scenario), (
                "missing scenario: " + scenario
            )
        assert "read" in m["probes"]
        assert m["help_version"]["precedence"] in {"help", "version", "first"}
        assert isinstance(m["help_version"]["trailing_options"], str)
        assert m["help_version"]["cases"], "declare eager argv cases"
        kinds = {case["kind"] for case in m["help_version"]["cases"]}
        assert kinds == {"text", "version"}, "declare help and version cases"
        for kind in kinds:
            cases = [c for c in m["help_version"]["cases"] if c["kind"] == kind]
            assert any(c["json"] for c in cases), "declare exact JSON help/version argv"
            assert any(not c["json"] for c in cases), "declare plain help/version argv"
        assert any(c["command"] == m["name"] for c in m["help_version"]["cases"])
        assert any(
            c["command"] in m["command_tree"] for c in m["help_version"]["cases"]
        )
        eager_cases = m["help_version"]["cases"]
        for first, second in (("--help", "--version"), ("--version", "--help")):
            combined = [
                c
                for c in eager_cases
                if first in c["argv"]
                and second in c["argv"]
                and c["argv"].index(first) < c["argv"].index(second)
            ]
            assert combined, "declare both combined help/version orders"
            winner = (
                first
                if m["help_version"]["precedence"] == "first"
                else "--" + m["help_version"]["precedence"]
            )
            kind = "text" if winner == "--help" else "version"
            assert all(c["kind"] == kind for c in combined), (
                "precedence declaration disagrees with argv cases"
            )
        assert any(
            "--quiet" in c["argv"] and "--verbose" in c["argv"] for c in eager_cases
        ), "declare eager precedence over flag conflicts"
        for concept in (
            "usage",
            "arguments",
            "defaults",
            "examples",
            "side effects",
            "exit codes",
            "configuration precedence",
            "project",
            "config",
            "schema",
            "mapping",
            "simultaneous failures",
        ):
            assert concept in m["help_required"], (
                "declare help documentation token: " + concept
            )
        prefixes = {
            " ".join(c.split()[:i])
            for c in m["command_tree"]
            for i in range(1, len(c.split()) + 1)
        }
        assert all(p["command"] in prefixes for p in m["probes"].values()), (
            "probes must name canonical resolved paths"
        )
        for alias in m["aliases"]:
            assert alias["canonical"] in m["command_tree"]
        if "mutation" in m["probes"]:
            retry = m["retry"]
            assert retry["flag"].startswith("--") and retry["receipt_field"]
            assert retry["scope"] and retry["retention"] and retry["conflict_code"]
            assert "scope" in m["help_required"] and "retention" in m["help_required"]
            for scenario in ("lost-response", "expiry"):
                assert scenario in m["probes"], "mutations require " + scenario
            for scenario in ("mutation", "lost-response"):
                assert m["probes"][scenario]["equivalent_argv"], (
                    "declare normalized equivalent input"
                )

    def probe(self, name: str, argv=None, reset=True) -> tuple:
        spec = self.manifest["probes"][name]
        if reset:
            self.fixture("reset", name)
        before = self.fixture("inspect", name)
        result = self.run(spec["argv"] if argv is None else argv)
        docs = self.decode(result.stdout, name.startswith("stream"))
        last = docs[-1]
        assert last["command"] == spec["command"], "report deepest canonical command"
        expected = CODES.get(name, spec.get("exit", 0))
        legacy = self.manifest.get("legacy_exits", {})
        actual = legacy.get(str(result.returncode), result.returncode)
        assert actual == expected and result.returncode != 1, "exit category mismatch"
        assert (actual == 0) == last["ok"], "exit and success disagree"
        assert last["status"] == spec.get(
            "status", "completed" if expected == 0 else "failed"
        )
        for path, value in spec.get("expect", {}).items():
            assert lookup(last, path) == value, "postcondition mismatch: " + path
        after = self.fixture("inspect", name)
        if name.startswith("stream"):
            assert len({d["request_id"] for d in docs}) == 1, (
                "stream changed request ID"
            )
        assert after["prompts"] == 0, "non-TTY or JSON invocation prompted"
        assert after["effects"] - before["effects"] == spec.get("effects", 0), (
            "unexpected mutation count"
        )
        if name not in {"invalid-flag", "missing-input", "conflict"}:
            assert last["request_id"] in after["request_ids"], (
                "request ID was not forwarded"
            )
        if name == "mutation":
            assert (
                isinstance(last["data"]["idempotency_key"], str)
                and last["data"]["idempotency_key"]
            )
        if expected:
            assert last["errors"], "failure needs structured errors"
            if "error_codes" in spec:
                assert [e["code"] for e in last["errors"]] == spec["error_codes"]
        if name == "expiry":
            assert after["expired"] is True, (
                "fixture must actually expire the retry key"
            )
            assert last["data"]["next_action"] == spec["inspection_command"], (
                "expiry recovery must name the declared inspection command"
            )
        if name == "unknown-fields":
            assert after["unknown_fields_sent"] is True, (
                "fixture must inject unknown optional fields"
            )
        if name == "unknown-version":
            assert after["unknown_version_sent"] is True, (
                "fixture must inject an unsupported version"
            )
            assert last["errors"][0]["code"] == spec["error_codes"][0]
        if name == "multiple-errors":
            assert len(last["errors"]) >= 2, "retain simultaneous errors"
        if name == "partial-failure":
            assert actual != 0 and last["status"] == "failed"
            assert last["data"] is not None, "retain partial result"
        if last["status"] == "accepted":
            assert (
                isinstance(last["data"]["operation_id"], str)
                and last["data"]["operation_id"]
            )
            assert (
                isinstance(last["data"]["next_action"], str)
                and last["data"]["next_action"]
            )
            assert last["data"]["next_action"] == spec["inspection_command"]
        if last["status"] == "completed":
            assert after["postcondition"], "completion must assert a real postcondition"
        return result, docs, after

    def help_case(self, case: dict):
        self.fixture("reset", "unavailable")
        before = self.fixture("inspect")
        result = self.run(case["argv"])
        assert result.returncode == 0, "help/version must exit 0 offline"
        if case["json"]:
            doc = self.decode(result.stdout)[0]
            text = doc["data"][case["kind"]]
            assert doc["command"] == case["command"]
        else:
            text = result.stdout
        assert isinstance(text, str) and text.strip()
        if case["kind"] == "version":
            assert text == self.manifest["version"] or self.manifest["version"] in text
        else:
            required = self.manifest["help_required"]
            for token in required.values() if isinstance(required, dict) else required:
                assert token.lower() in text.lower(), "help missing " + token
        after = self.fixture("inspect")
        assert after["effects"] == before["effects"] and after["service_calls"] == 0

    def flag(self, flag: str, before: bool, name: str = "read"):
        spec = self.manifest["probes"][name]
        args = [a for a in spec["argv"] if a != "--json"]
        flags = [flag] + ([] if flag == "--json" else ["--json"])
        result, docs, state = self.probe(name, flags + args if before else args + flags)
        if flag == "--quiet":
            assert not result.stderr, "quiet leaked informational diagnostics"
        if flag == "--verbose":
            assert result.stderr.strip(), "verbose should add stderr diagnostics"

    def interaction(self, name: str, flags: list, tty: str = "none"):
        spec = self.manifest["probes"][name]
        args = [a for a in spec["argv"] if a != "--json"] + flags
        self.fixture("reset", name)
        result = self.run(args) if tty == "none" else self.terminal_run(args, tty)
        assert result.returncode == CODES[name], (
            "noninteractive missing input/decision must fail in its category"
        )
        state = self.fixture("inspect", name)
        assert state["prompts"] == 0 and state["effects"] == 0, (
            "must neither prompt nor mutate"
        )
        if "--json" in flags:
            self.decode(result.stdout)

    def alias(self, alias: dict, quiet=False):
        self.fixture("reset")
        result = self.run(alias["argv"] + (["--quiet"] if quiet else []))
        doc = self.decode(result.stdout)[-1]
        assert result.returncode == 0 and doc["command"] == alias["canonical"]
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        assert (
            len(lines) == 1
            and alias["canonical"] in lines[0]
            and "deprecat" in lines[0].lower()
        )
        canonical, docs, state = self.probe("read", alias["canonical_argv"])
        assert doc["data"] == docs[-1]["data"], "alias must preserve results"

    def generated_key(self):
        self.fixture("reset", "mutation")
        result = self.run(self.manifest["probes"]["mutation"]["argv"])
        doc = self.decode(result.stdout)[-1]
        assert result.returncode == 0
        assert (
            isinstance(doc["data"]["idempotency_key"], str)
            and doc["data"]["idempotency_key"]
        )

    def stable_error(self, name: str):
        _, first, _ = self.probe(name)
        _, second, _ = self.probe(name)
        assert [e["code"] for e in first[-1]["errors"]] == [
            e["code"] for e in second[-1]["errors"]
        ]

    def retry(self, scenario: str):
        spec = self.manifest["probes"][scenario]
        self.fixture("reset", scenario)
        key = "conformance-retry-key"
        argv = spec["argv"] + [self.manifest["retry"]["flag"], key]
        first = self.run(argv)
        if scenario == "lost-response":
            assert first.returncode != 0, "fixture must lose the response after commit"
            lost = self.decode(first.stdout)[-1]
            assert lost["status"] == "failed" and not lost["ok"]
            first_doc = None
        else:
            first_doc = self.decode(first.stdout)[-1]
            assert first.returncode == 0
        before = self.fixture("inspect", scenario)
        assert before["effects"] == 1, "first submission must commit once"
        equivalent = spec["equivalent_argv"] + [self.manifest["retry"]["flag"], key]
        second = self.run(equivalent)
        doc = self.decode(second.stdout)[-1]
        assert second.returncode == 0 and doc["ok"]
        after = self.fixture("inspect", scenario)
        assert after["effects"] == 1, "retry duplicated effects"
        assert lookup(doc, self.manifest["retry"]["receipt_field"]) == key
        assert doc["data"]["operation_id"] == before["operation_id"]
        assert doc["request_id"] == before["request_id"]
        if first_doc:
            assert (
                doc["data"] == first_doc["data"]
                and doc["request_id"] == first_doc["request_id"]
            )
        conflict = self.run(argv + spec["different_input"])
        failed = self.decode(conflict.stdout)[-1]
        assert conflict.returncode == 2 and not failed["ok"]
        assert failed["errors"][0]["code"] == self.manifest["retry"]["conflict_code"]
        assert self.fixture("inspect", scenario)["effects"] == 1

    def receipts(self):
        spec = self.manifest["probes"]["acceptance"]
        _, accepted, state = self.probe("acceptance")
        result = self.run(spec["inspection_argv"])
        completed = self.decode(result.stdout)[-1]
        assert result.returncode == 0 and completed["status"] == "completed"
        for path in ("data.operation_id", "request_id"):
            assert lookup(accepted[-1], path) == lookup(completed, path)
        assert self.fixture("inspect")["postcondition"]

    def execute(self) -> list:
        self.check(
            "manifest",
            "manifest",
            self.validate_manifest,
            "Publish manifest version 1 with all required scenarios or explicit reasons.",
        )
        if not self.results[-1]["passed"]:
            return self.results
        for index, case in enumerate(self.manifest["help_version"]["cases"]):
            self.check(
                "help-version/" + str(index),
                "commands",
                lambda c=case: self.help_case(c),
                "Render declared scope offline, before operand/conflict checks, without service calls.",
            )
        for name in self.manifest["probes"]:
            if name in {"lost-response", "mutation"}:
                continue
            self.check(
                "probe/" + name,
                "exits" if name in CODES else "output",
                lambda n=name: self.probe(n),
                "Emit one typed canonical envelope, correct exit/status, no prompts or unintended effects.",
            )
        for name in ("invalid-input", "unavailable", "unknown-version"):
            if name in self.manifest["probes"]:
                self.check(
                    "stable-error/" + name,
                    "output",
                    lambda n=name: self.stable_error(n),
                    "Keep stable error codes across repeated failures.",
                )
        if "mutation" in self.manifest["probes"]:
            self.check(
                "generated-retry-key",
                "work",
                self.generated_key,
                "Include generated retry keys in acknowledgement data.idempotency_key.",
            )
        safe_commands = {}
        for name, spec in self.manifest["probes"].items():
            if (
                name not in CODES
                and spec.get("exit", 0) == 0
                and not name.startswith("stream")
                and name != "lost-response"
            ):
                safe_commands.setdefault(spec["command"], name)
        for command, name in safe_commands.items():
            for flag in SHARED:
                for before in (True, False):
                    self.check(
                        "flag/"
                        + command
                        + "/"
                        + flag
                        + ("/before" if before else "/after"),
                        "commands",
                        lambda f=flag, b=before, n=name: self.flag(f, b, n),
                        "Accept shared flags on either side of the command; keep diagnostics on stderr.",
                    )
        for name in ("missing-input", "confirmation", "owner-decision", "denial"):
            if name in self.manifest["probes"]:
                variants = [[], ["--no-input"], ["--json"]]
                if name in {"missing-input", "denial"}:
                    variants.append(["--yes", "--json"])
                for index, flags in enumerate(variants):
                    self.check(
                        "interaction/" + name + "/" + str(index),
                        "output",
                        lambda n=name, f=flags: self.interaction(n, f),
                        "Fail without prompting or mutation; --yes cannot supply inputs or authorization.",
                    )
        if os.name == "posix":
            for name in ("missing-input", "confirmation"):
                if name in self.manifest["probes"]:
                    for tty, flags in (
                        ("stdin", []),
                        ("stdout", []),
                        ("both", ["--no-input"]),
                        ("both", ["--json"]),
                    ):
                        self.check(
                            "tty/" + name + "/" + tty + "/" + ",".join(flags),
                            "output",
                            lambda n=name, f=flags, t=tty: self.interaction(n, f, t),
                            "Never prompt when either stream is non-TTY, or JSON/no-input is selected.",
                        )
        for index, alias in enumerate(self.manifest["aliases"]):
            self.check(
                "alias/" + str(index),
                "commands",
                lambda a=alias: self.alias(a),
                "Warn once on stderr, preserve behavior, and return the canonical command.",
            )
        for scenario in ("mutation", "lost-response"):
            if scenario in self.manifest["probes"]:
                self.check(
                    "retry/" + scenario,
                    "work",
                    lambda s=scenario: self.retry(s),
                    "Deduplicate committed retries and reject changed input with a stable conflict error.",
                )
        for index, alias in enumerate(self.manifest["aliases"]):
            self.check(
                "quiet-alias/" + str(index),
                "commands",
                lambda a=alias: self.alias(a, True),
                "Retain the single deprecation warning when quiet is selected.",
            )
        if "acceptance" in self.manifest["probes"]:
            self.check(
                "receipts",
                "work",
                self.receipts,
                "Retain operation/request IDs from acceptance through verified completion.",
            )
        return self.results


def lookup(value: Any, path: str) -> Any:
    for part in path.split("."):
        value = value[part]
    return value


def check_manifest(path: Path) -> list:
    with path.open(encoding="utf-8") as source:
        manifest = json.load(source)
    artifact_root = Path(
        os.environ.get("MATILDA_ARTIFACT_ROOT", "/var/tmp/matilda/workspace")
    )
    artifact_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="goobits-conformance-", dir=artifact_root
    ) as state:
        return Suite(manifest, path.resolve().parent, state).execute()
