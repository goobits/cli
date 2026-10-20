"""Manifest-driven, isolated subprocess assertions. Never imports target code."""

import json
import os
import re
import subprocess
import tempfile
import threading
from importlib.metadata import distribution, files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SECTIONS = {
    "commands": "commands-and-flags",
    "output": "interaction-and-output",
    "exits": "exit-codes",
    "work": "work-retries-and-versions",
    "manifest": "conformance-interface",
}
# One contract table owns applicability, exits, required inputs and observations.
# fmt: off
CONTRACTS = {
    "read": {}, "missing-input": {"exit": 2, "interaction": "no-bypass"}, "invalid-input": {"exit": 2, "stable": True},
    "invalid-flag": {"exit": 2}, "conflict": {"exit": 2}, "confirmation": {"exit": 4, "yes_variant": "confirmation-yes", "requires": ("confirmation-yes",), "interaction": "decision"},
    "confirmation-yes": {}, "owner-decision": {"exit": 4, "interaction": "decision"}, "denial": {"exit": 4, "interaction": "no-bypass"},
    "unavailable": {"exit": 5, "stable": True}, "verification": {"exit": 3},
    "timeout": {"exit": 124}, "interrupt": {"exit": 130},
    "partial-failure": {"observe": lambda d, s, p: d["status"] == "failed" and d["data"] is not None},
    "multiple-errors": {"observe": lambda d, s, p: len(d["errors"]) >= 2},
    "acceptance": {"status": "accepted", "fields": ("inspection_command", "inspection_argv"), "also": ("receipts", "receipts", ())},
    "completion": {}, "stream": {}, "stream-failure": {},
    "mutation": {"method": "retry", "fields": ("different_input", "equivalent_argv"), "requires": ("lost-response", "expiry"), "also": ("generated-retry-key", "probe", ("mutation",))},
    "lost-response": {"method": "retry", "fields": ("different_input", "equivalent_argv")},
    "unknown-fields": {"observe": lambda d, s, p: s["unknown_fields_sent"] and bool(s["upstream_messages"])},
    "unknown-version": {"exit": 2, "stable": True, "fields": ("error_codes",),
                        "observe": lambda d, s, p: s["unknown_version_sent"] and bool(s["upstream_messages"])},
    "expiry": {"fields": ("inspection_command",), "observe": lambda d, s, p:
               s["expired"] and bool(s["expired_entries"]) and d["data"]["next_action"] == p["inspection_command"]},
}
# id, argv tokens ($leaf/$missing expand declared paths), kind, JSON recognition, scope
HELP_CASES = (
    ("root-help",             ("--help",),                            "text",    "plain",    "root"),
    ("root-help-command",     ("--help", "$leaf"),                   "text",    "plain",    "root"),
    ("leaf-help",             ("$leaf", "--help"),                   "text",    "plain",    "leaf"),
    ("root-version",          ("--version",),                         "version", "plain",    "root"),
    ("help-missing-input",    ("$missing", "--help"),                "text",    "plain",    "missing"),
    ("version-missing-input", ("$missing", "--version"),             "version", "plain",    "missing"),
    ("text-conflict",         ("$leaf", "--help", "--quiet", "--verbose"), "text", "plain", "leaf"),
    ("version-conflict",      ("$leaf", "--version", "--quiet", "--verbose"), "version", "plain", "leaf"),
    ("json-help-before",      ("--json", "$leaf", "--help"),         "text",    "json",     "leaf"),
    ("json-help-after",       ("$leaf", "--help", "--json"),         "text",    "trailing", "leaf"),
    ("json-version-before",   ("--json", "$leaf", "--version"),      "version", "json",     "leaf"),
    ("json-version-after",    ("$leaf", "--version", "--json"),      "version", "trailing", "leaf"),
    ("help-version",          ("--help", "--version"),               "help",    "plain",    "root"),
    ("version-help",          ("--version", "--help"),               "version", "plain",    "root"),
)
# fmt: on
SCENARIOS = set(CONTRACTS) - {"confirmation-yes"}
CODES = {name: c["exit"] for name, c in CONTRACTS.items() if "exit" in c}
TERMINAL_STATUSES = {"accepted", "completed", "failed"}
SHARED = ("--json", "--quiet", "--verbose", "--yes", "--no-input")
# fmt: off
FLAG_CASES = {
    "replace": ("--json", "--quiet", "--verbose"),
    "dependencies": {"--quiet": ("volatile_paths", "diagnostics"), "--verbose": ("volatile_paths",)},
    "shared": [(flag, before) for flag in SHARED for before in (True, False)],
    "decision": [("none", []), ("none", ["--no-input"]), ("none", ["--json"])],
    "tty": [("stdin", []), ("stdout", []), ("both", ["--no-input"]), ("both", ["--json"])],
}
# fmt: on
FLAG_CASES["no-bypass"] = FLAG_CASES["decision"] + [("none", ["--yes", "--json"])]
HELP_TOPICS = (
    "usage|arguments|defaults|examples|side effects|exit codes|"
    "configuration precedence|project|config|schema|mapping|simultaneous failures"
).split("|")


def help_matrix(manifest, rows=HELP_CASES):
    """Materialize required cases once, for both validation and execution."""
    h, cases = manifest["help_version"], []
    for case_id, tokens, kind, machine, scope in rows:
        argv = [
            arg
            for token in tokens
            for arg in (h[token[1:] + "_argv"] if token.startswith("$") else [token])
        ]
        if case_id in {"help-version", "version-help"}:
            winner = kind if h["precedence"] == "first" else h["precedence"]
            kind = "text" if winner == "help" else "version"
        command = manifest["name"] if scope == "root" else h[scope + "_command"]
        case = {"id": case_id, "argv": argv, "kind": kind, "command": command}
        case["json"] = machine == "json" or (
            machine == "trailing" and h["trailing_options"] == "recognized"
        )
        cases.append(case)
    return cases


def envelope_errors(doc: Any, stream: bool = False) -> list:
    """Return type/semantic violations, allowing unknown optional fields."""
    if not isinstance(doc, dict):
        return ["envelope must be an object"]
    types = {
        "schema_version": int,
        "command": str,
        "ok": bool,
        "errors": list,
        "request_id": str,
        "status": str,
    }
    errors = [
        key + " has wrong or missing type"
        for key, kind in types.items()
        if type(doc.get(key)) is not kind
    ]
    if "data" not in doc:
        errors.append("data is missing")
    if errors:
        return errors
    if doc["schema_version"] != 1:
        errors.append("unsupported schema_version")
    if not doc["request_id"].strip() or not doc["command"].strip():
        errors.append("empty request_id or command")
    statuses = TERMINAL_STATUSES | ({"running"} if stream else set())
    if doc["status"] not in statuses:
        errors.append("invalid status")
    if doc["ok"] != (not doc["errors"]) or doc["ok"] != (doc["status"] != "failed"):
        errors.append("ok/errors/status disagree")
    for error in doc["errors"]:
        if not isinstance(error, dict):
            errors.append("error must be an object")
            continue
        fields = {
            "code": (str,),
            "message": (str,),
            "retryable": (bool,),
            "next_action": (str,),
            "target": (str, type(None)),
        }
        errors.extend(
            "error." + k + " has wrong or missing type"
            for k, kinds in fields.items()
            if k not in error or type(error[k]) not in kinds
        )
        errors.extend(
            "error." + k + " is empty"
            for k in ("code", "next_action")
            if not error.get(k)
        )
    return errors


def documents(stdout: str, stream: bool = False, mapping=None) -> list:
    if not stdout.endswith("\n") or "\x1b" in stdout:
        raise ValueError("stdout needs a final newline and no terminal controls")

    def reject_constant(value):
        raise ValueError("non-JSON number: " + value)

    decoder = json.JSONDecoder(parse_constant=reject_constant)
    if stream:
        docs = [decoder.decode(line) for line in stdout.splitlines()]
    else:
        doc, end = decoder.raw_decode(stdout.lstrip())
        assert stdout.lstrip()[end:] == "\n", (
            "exactly one JSON document followed by one newline is required"
        )
        docs = [doc]
    if mapping:
        docs = [map_envelope(doc, mapping) for doc in docs]
    if stream and (not docs or docs[-1].get("status") not in TERMINAL_STATUSES):
        raise ValueError("stream needs a terminal receipt")
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
    # fmt: off
    def __init__(self, manifest: dict, base: Path, state: str):
        self.manifest, self.raw_manifest = (manifest if isinstance(manifest, dict) else {}), manifest
        manifest = self.manifest
        self.base = base
        self.results = []
        self.baselines = {}
        self.env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "LANG") if k in os.environ}
        self.env.update(HOME=state, TMPDIR=state, NO_COLOR="1", TERM="dumb",
                        PYTHONDONTWRITEBYTECODE="1", GOOBITS_CONFORMANCE_STATE=state)
        fixture = manifest.get("fixture", {})
        if isinstance(fixture, dict) and isinstance(fixture.get("env", {}), dict):
            self.env.update(fixture.get("env", {}))

    # fmt: on
    def check(self, rule: str, section: str, action, hint: str) -> None:
        try:
            action()
            passed, detail = True, ""
        except (
            AssertionError,
            AttributeError,
            ValueError,
            LookupError,
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
        env = dict(self.env, TERM="xterm-256color", FORCE_COLOR="1")
        env.pop("NO_COLOR", None)

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
                env=env,
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

    # fmt: off
    def validate_manifest(self, collect=False):
        """Evaluate every independent declaration; paths also identify dependencies."""
        m, rules = self.manifest, {}
        schema = Path(__file__).resolve().parents[3] / "docs/conformance-manifest.schema.json"
        if not schema.is_file():
            schema = distribution("goobits-cli").locate_file(next(p for p in files("goobits-cli") or () if str(p).endswith("share/goobits-cli/docs/conformance-manifest.schema.json")))
            schema = schema if schema.is_file() else Path(__file__).resolve().parents[2] / "share/goobits-cli/docs" / schema.name
        for error in Draft202012Validator(json.loads(schema.read_text(encoding="utf-8")), format_checker=Draft202012Validator.FORMAT_CHECKER).iter_errors(self.raw_manifest):
            keys = [k for k in error.validator_value if k not in error.instance] if error.validator == "required" else [k for k in error.instance if k not in error.schema.get("properties", {})] if error.validator == "additionalProperties" else [None]
            for key in keys:
                path = ".".join(map(str, [*error.path, *([] if key is None else [key])])) or "$"
                rules.setdefault(path, path + ": " + ("required declaration is missing" if error.validator == "required" else error.message))

        def rule(path, test, hint="invalid or missing declaration"):
            try:
                assert test(), hint
            except (AssertionError, LookupError, TypeError, AttributeError, ValueError, StopIteration) as exc:
                rules.setdefault(path, path + ": " + (str(exc) or hint))
        rule("long_flags", lambda: bool(m.get("long_flags")))
        probes = m.get("probes") if isinstance(m.get("probes"), dict) else {}
        tree = m.get("command_tree") if isinstance(m.get("command_tree"), list) else []
        for index, command in enumerate(tree):
            rule(f"command_tree.{index}", lambda command=command: command.split()[0] == m["name"] and (len(command.split()) >= 3 or command in m.get("entrypoint_exceptions", [])) and all(re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", p) for p in command.split()))
        for name in sorted(SCENARIOS):
            rule("probes." + name, lambda name=name: name in probes or bool(m["inapplicable"].get(name)), "missing scenario")
        prefixes = {" ".join(c.split()[:i]) for index, c in enumerate(tree) if isinstance(c, str) and f"command_tree.{index}" not in rules for i in range(1, len(c.split()) + 1)}
        for name, spec in probes.items():
            path = "probes." + name
            for field in CONTRACTS.get(name, {}).get("fields", ()):
                rule(path + "." + field, lambda field=field, spec=spec: bool(spec[field]), "scenario requires " + field)
        cases, flags, h = self.command_cases(), m.get("flag_probes", {}), m.get("help_version") if isinstance(m.get("help_version"), dict) else {}
        for command in dict.fromkeys([*[c for c in tree if isinstance(c, str)], *(flags if isinstance(flags, dict) else {})]):
            rule("flag_probes." + command, lambda command=command: command in tree and command in cases and bool(cases[command][1].get("argv")) and cases[command][1]["command"] == command, "flag probe must reference a usable probe for a declared command")
        references = [
            *[(f"entrypoint_exceptions.{i}", c, tree) for i, c in enumerate(m.get("entrypoint_exceptions", []) if isinstance(m.get("entrypoint_exceptions"), list) else [])],
            *[("inapplicable." + n, n, SCENARIOS) for n in (m.get("inapplicable", {}) if isinstance(m.get("inapplicable"), dict) else {})],
            *[(f"probes.{n}.{f}", p.get(f), prefixes if f == "command" else [p[f]] if isinstance(p.get(f), str) and any(p[f] == c or p[f].startswith(c + " ") for i, c in enumerate(tree) if isinstance(c, str) and f"command_tree.{i}" not in rules) else []) for n, p in probes.items() if isinstance(p, dict) for f in ("command", "inspection_command") if f in p],
            *[(f"aliases.{i}.canonical", a.get("canonical"), [c for j, c in enumerate(tree) if f"command_tree.{j}" not in rules]) for i, a in enumerate(m.get("aliases", []) if isinstance(m.get("aliases"), list) else []) if isinstance(a, dict)],
            *[("help_version." + f, h.get(f), prefixes) for f in ("leaf_command", "missing_command")],
            *[("help_version.scope_usage." + c, c, prefixes) for c in (h.get("scope_usage", {}) if isinstance(h.get("scope_usage"), dict) else {})],
        ]
        for path, value, choices in references:
            rule(path, lambda value=value, choices=choices: value in choices, "reference must name a declared command or scenario")
        if "missing-input" in probes:
            for field, expected in {"missing_argv": lambda: [a for a in probes["missing-input"]["argv"] if a not in SHARED], "missing_command": lambda: probes["missing-input"]["command"]}.items():
                rule("help_version." + field, lambda expected=expected, field=field: h[field] == expected(), "missing-input help case must use the actual missing invocation")
        for index, (case_id, *_) in enumerate(HELP_CASES):
            rule("help_version.cases." + case_id, lambda case_id=case_id, index=index: next(c for c in h["cases"] if isinstance(c, dict) and c.get("id") == case_id) == help_matrix(m, (HELP_CASES[index],))[0], "missing or inconsistent help matrix case: " + case_id)
        seen = set()
        for index, case in enumerate(h.get("cases", []) if isinstance(h.get("cases"), list) else []):
            if isinstance(case, dict) and isinstance(case.get("id"), str):
                rule(f"help_version.cases.{index}.id", lambda case=case: case["id"] not in seen, "case IDs must be unique")
                seen.add(case["id"])
                rule(f"help_version.cases.{index}.command", lambda case=case: case["command"] in prefixes and (case.get("kind") != "text" or case["command"] in h["scope_usage"]), "help case must name a canonical scope with declared usage")
        docs = m.get("help_required") if isinstance(m.get("help_required"), dict) else {}
        for topic in HELP_TOPICS:
            rule("help_required." + topic, lambda topic=topic: isinstance(docs[topic], str) and len(docs[topic].strip()) > len(topic) + 3, "help documentation: " + topic)
        rule("help_required.schema", lambda: str(m["payload_schema"]["version"]) in docs["schema"] and m["payload_schema"]["identifier"] in docs["schema"])
        legacy = m.get("legacy_exits", {})
        rule("legacy_exits", lambda: isinstance(legacy, dict) and all(k.isdecimal() and type(v) is int and v in {0, 2, 3, 4, 5, 124, 130} and (k != "1" or v != 0) for k, v in legacy.items()))
        if isinstance(legacy, dict):
            for code in ((0,) if legacy else (0, 1, 2, 3, 4, 5, 124, 130)):
                rule("help_required.exit codes." + str(code), lambda code=code: bool(re.search(r"(?<![0-9])" + str(code) + r"(?![0-9])", docs["exit codes"])), "document exit mappings")
        if "mutation" in probes:
            for field in ("scope", "retention"):
                rule("retry." + field, lambda field=field: m["retry"][field] in docs[field])
        if not collect:
            assert not rules, "; ".join(rules.values())
        return list(rules.items())

    # fmt: on
    def category(self, result, expected=None):
        legacy = self.manifest.get("legacy_exits", {})
        if result.returncode == 1:
            assert legacy.get("1") in {2, 3, 4, 5, 124, 130}, (
                "reserved exit 1 denotes a crash"
            )
            assert expected != 0, "legacy exit 1 always denotes failure"
            return expected if expected is not None else legacy["1"]
        return legacy.get(str(result.returncode), result.returncode)

    # fmt: off
    def command_cases(self):
        probes = self.manifest.get("probes") if isinstance(self.manifest.get("probes"), dict) else {}
        cases = {p["command"]: (n, p) for n, p in reversed(list(probes.items()))
                 if n != "lost-response" and isinstance(p, dict) and isinstance(p.get("command"), str)}
        flags = self.manifest.get("flag_probes", {})
        for command, name in (flags if isinstance(flags, dict) else {}).items():
            cases[command] = (name, probes[name] if isinstance(name, str) and isinstance(probes.get(name), dict) else {"command": command})
        for name, spec in probes.items():
            if isinstance(spec, dict) and isinstance(spec.get("inspection_command"), str):
                inspection = dict(spec, argv=spec.get("inspection_argv"), command=spec["inspection_command"],
                                  status="completed", effects=spec.get("inspection_effects", 0), setup_argv=spec.get("argv", []), _inspection=True)
                cases.setdefault(spec["inspection_command"], (name, inspection))
        tree = self.manifest.get("command_tree", [])
        declared = [c if isinstance(c, str) else f"@{i}" for i, c in enumerate(tree if isinstance(tree, list) else [])]
        return {c: cases.get(c, ("read", {"command": c})) for c in [*declared, *(flags if isinstance(flags, dict) else {}), *(cases if not isinstance(tree, list) else {})]}
    # fmt: on

    def probe(self, name: str, argv=None, reset=True, spec=None, tty="none") -> tuple:
        spec = spec or self.manifest["probes"][name]
        contract = CONTRACTS.get(name, {})
        if reset:
            before = self.fixture("reset", name)
            if spec.get("setup_argv"):
                self.run(spec["setup_argv"])
                before = self.fixture("inspect", name)
        else:
            before = self.fixture("inspect", name)
        argv = spec["argv"] if argv is None else argv
        result = self.run(argv) if tty == "none" else self.terminal_run(argv, tty)
        docs = self.decode(result.stdout, spec.get("stream", name.startswith("stream")))
        last = docs[-1]
        assert last["command"] == spec["command"], "report deepest canonical command"
        expected = contract.get("exit", spec.get("exit", 0))
        actual = self.category(result, expected)
        assert actual == expected, "exit category mismatch"
        assert (actual == 0) == last["ok"], "exit and success disagree"
        assert last["status"] == spec.get(
            "status", contract.get("status", "completed" if expected == 0 else "failed")
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
        if after["service_calls"] > before["service_calls"] or spec.get(
            "dispatch", False
        ):
            assert last["request_id"] in after["request_ids"], (
                "request ID was not forwarded"
            )
        fields = ["idempotency_key"] if name == "mutation" else []
        if last["status"] == "accepted":
            fields += ["operation_id", "next_action"]
            assert last["data"]["next_action"] == spec["inspection_command"]
        for field in fields:
            assert isinstance(last["data"][field], str) and last["data"][field], (
                "receipt field: " + field
            )
        if expected:
            assert last["errors"], "failure needs structured errors"
            if "error_codes" in spec:
                assert [e["code"] for e in last["errors"]] == spec["error_codes"]
        if "observe" in contract:
            assert contract["observe"](last, after, spec), (
                "scenario observation/postcondition mismatch: " + name
            )
        if last["status"] == "completed":
            assert after["postcondition"], "completion must assert a real postcondition"
        return result, docs, after

    def help_case(self, case: dict):
        before = self.fixture("reset", "unavailable")
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
            assert self.manifest["version"] in text
        else:
            usage = self.manifest["help_version"]["scope_usage"][case["command"]]
            assert usage in text, "help documentation has the wrong parser scope"
            for topic, passage in self.manifest["help_required"].items():
                assert " ".join(passage.split()) in " ".join(text.split()), (
                    "help documentation missing: " + topic
                )
            for code, category in self.manifest.get("legacy_exits", {}).items():
                assert (
                    code in text
                    and str(category) in text
                    and self.manifest["canonical_exit_invocation"] in text
                    and "deprecat" in text.lower()
                )
        after = self.fixture("inspect")
        assert after["effects"] == before["effects"] and after["service_calls"] == 0

    def stable_result(self, docs):
        docs = json.loads(json.dumps(docs))
        for doc in docs:
            for path in ["request_id"] + self.manifest.get("volatile_paths", []):
                value = doc
                parts = path.split(".")
                for part in parts[:-1]:
                    value = value.get(part, {}) if isinstance(value, dict) else {}
                if isinstance(value, dict):
                    value.pop(parts[-1], None)
        return docs

    def flag(self, flag: str, before: bool, name: str = "read", spec=None):
        spec = spec or self.manifest["probes"][name]
        key = json.dumps([name, spec], sort_keys=True)
        if key not in self.baselines:
            self.baselines[key] = self.probe(name, spec=spec)
        baseline, original, _ = self.baselines[key]
        replace = {*FLAG_CASES["replace"], flag}
        args = [a for a in spec["argv"] if a not in replace]
        flags = [flag] + ([] if flag == "--json" else ["--json"])
        variant = (
            CONTRACTS.get(name, {}).get("yes_variant") if flag == "--yes" else None
        )
        selected = self.manifest["probes"][variant] if variant else spec
        result, docs, _ = self.probe(
            variant or name, flags + args if before else args + flags, spec=selected
        )
        if flag in {"--verbose", "--quiet"}:
            assert self.stable_result(docs) == self.stable_result(original), (
                "flag changed stdout result"
            )
        if flag == "--quiet":
            allowed = self.manifest.get("diagnostics", {})
            patterns = allowed.get("error", []) + allowed.get("deprecation", [])
            messages = [e["message"] for d in docs for e in d["errors"]]

            def permitted(line):
                return line in messages or any(re.fullmatch(p, line) for p in patterns)

            assert all(permitted(line) for line in result.stderr.splitlines()), (
                "quiet leaked informational diagnostics"
            )
            assert all(
                line in result.stderr.splitlines()
                for line in baseline.stderr.splitlines()
                if permitted(line)
            ), "quiet dropped required diagnostics"
        if flag == "--verbose":
            assert result.stderr.strip(), "verbose should add stderr diagnostics"

    def json_terminal(self, name="read", spec=None):
        self.probe(name, spec=spec, tty="both")

    def interaction(self, name: str, flags: list, tty: str = "none"):
        spec = self.manifest["probes"][name]
        args = [a for a in spec["argv"] if a != "--json"] + flags
        self.fixture("reset", name)
        result = self.run(args) if tty == "none" else self.terminal_run(args, tty)
        assert self.category(result, CODES[name]) == CODES[name], (
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
        assert self.category(result, 0) == 0 and doc["command"] == alias["canonical"]
        lines = [line for line in result.stderr.splitlines() if line.strip()]
        assert (
            len(lines) == 1
            and alias["canonical"] in lines[0]
            and "deprecat" in lines[0].lower()
        )
        canonical, docs, state = self.probe("read", alias["canonical_argv"])
        assert doc["data"] == docs[-1]["data"], "alias must preserve results"

    def stable_error(self, name: str):
        codes = [
            [e["code"] for e in self.probe(name)[1][-1]["errors"]] for _ in range(2)
        ]
        assert codes[0] == codes[1]

    def retry(self, scenario: str):
        spec = self.manifest["probes"][scenario]
        self.fixture("reset", scenario)
        key = "conformance-retry-key"
        argv = spec["argv"] + [self.manifest["retry"]["flag"], key]
        first = self.run(argv)
        first_doc = self.decode(first.stdout)[-1]
        expected = 5 if scenario == "lost-response" else 0
        assert self.category(first, expected) == expected
        assert first_doc["ok"] == (expected == 0)
        before = self.fixture("inspect", scenario)
        assert before["effects"] == 1, "first submission must commit once"
        equivalent = spec["equivalent_argv"] + [self.manifest["retry"]["flag"], key]
        second = self.run(equivalent)
        doc = self.decode(second.stdout)[-1]
        assert self.category(second, 0) == 0 and doc["ok"]
        after = self.fixture("inspect", scenario)
        assert after["effects"] == 1, "retry duplicated effects"
        assert lookup(doc, self.manifest["retry"]["receipt_field"]) == key
        assert doc["data"]["operation_id"] == before["operation_id"]
        assert doc["request_id"] == before["request_id"]
        if scenario != "lost-response":
            assert (
                doc["data"] == first_doc["data"]
                and doc["request_id"] == first_doc["request_id"]
            )
        conflict = self.run(argv + spec["different_input"])
        failed = self.decode(conflict.stdout)[-1]
        assert self.category(conflict, 2) == 2 and not failed["ok"]
        assert failed["errors"][0]["code"] == self.manifest["retry"]["conflict_code"]
        assert self.fixture("inspect", scenario)["effects"] == 1

    def receipts(self):
        spec = self.manifest["probes"]["acceptance"]
        _, accepted, state = self.probe("acceptance")
        result = self.run(spec["inspection_argv"])
        completed = self.decode(result.stdout)[-1]
        assert self.category(result, 0) == 0 and completed["status"] == "completed"
        for path in ("data.operation_id", "request_id"):
            assert lookup(accepted[-1], path) == lookup(completed, path)
        assert self.fixture("inspect")["postcondition"]

    # fmt: off
    def execute(self) -> list:
        problems = self.validate_manifest(collect=True) or []
        for path, detail in problems:
            self.check("manifest/" + path, "manifest", lambda: None, "Correct " + path)
            self.results[-1].update(passed=False, detail=detail)
        if not problems:
            self.check("manifest", "manifest", lambda: None, "Keep declarations current")
        probes = self.manifest.get("probes") if isinstance(self.manifest.get("probes"), dict) else {}

        def check(rule, section, fn, *args, needs=()):
            needs = list(needs) + ["$", "manifest_version", "executable", "fixture", "timeout_seconds"]
            if rule.startswith("help-version/"):
                case = args[0] if isinstance(args[0], dict) else {}
                needs += ["help_version.trailing_options"] if any(r[0] == case.get("id") and r[3] == "trailing" for r in HELP_CASES) else []
                needs += ["help_version.precedence"] if case.get("id") in ("help-version", "version-help") else []
                needs += (["help_version.cases." + case["id"]] if isinstance(case.get("id"), str) and case["id"] in {r[0] for r in HELP_CASES} else []) + (["envelope_mapping"] if case.get("json") else []) + (["version"] if case.get("kind") == "version" else ["help_required", "help_version.scope_usage." + str(case.get("command")), "canonical_exit_invocation", "legacy_exits"])
            else:
                needs += ["legacy_exits", "envelope_mapping"]
                name = args[2] if rule.startswith("flag/") else args[0] if args else "acceptance"
                if isinstance(name, str):
                    needs += ["probes." + name + "." + f for f in "argv command exit expect effects status stream dispatch error_codes setup_argv inspection_command".split()]
                    if rule == "receipts":
                        needs += ["probes.acceptance.inspection_argv"]
                    if rule.startswith(("flag/", "json/color-capable-tty/")) and isinstance(args[-1], dict) and args[-1].get("_inspection"):
                        needs += ["probes." + name + "." + f for f in "inspection_argv inspection_effects".split()]
                    if rule.startswith("retry/"):
                        needs += ["retry", "probes." + name]
                    if name not in probes:
                        needs += ["inapplicable." + name]
                    if rule.startswith("flag/"):
                        needs += list(FLAG_CASES["dependencies"].get(args[0], ()))
                        if args[0] == "--yes" and CONTRACTS.get(name, {}).get("yes_variant"):
                            needs += ["probes." + CONTRACTS[name]["yes_variant"]]
                if rule.startswith("alias/"):
                    needs += ["aliases." + rule.split("/")[1], "probes.read"]
            blocked = [detail for path, detail in problems if any(path == n or path.startswith(n + ".") or n.startswith(path + ".") for n in needs)]
            hint = f"Apply docs/cli-standard.md#{SECTIONS[section]}; {rule}"
            self.check(rule, section, lambda: None if blocked else fn(*args), hint)
            if blocked:
                self.results[-1].update(passed=None, skipped=True, detail="Depends on: " + "; ".join(blocked))

        legacy = self.manifest.get("legacy_exits", {})
        if isinstance(legacy, dict) and legacy and not any(p == "legacy_exits" for p, _ in problems):
            self.check("legacy-exits/deprecated", "exits", lambda: None, "Adopt canonical exits via the documented invocation")
            self.results[-1].update(warning=True, detail="Legacy exit mapping is deprecated: " + json.dumps(legacy))
        h = self.manifest.get("help_version", {})
        supplied = h.get("cases", []) if isinstance(h, dict) and isinstance(h.get("cases", []), list) else []
        first = {c["id"]: i for i, c in reversed(list(enumerate(supplied))) if isinstance(c, dict) and isinstance(c.get("id"), str)}
        for index, case in [(None, {"id": r[0]}) for r in HELP_CASES if r[0] not in first] + list(enumerate(supplied)):
            label = case.get("id") if isinstance(case, dict) and isinstance(case.get("id"), str) else f"@{index}"
            label = label if first.get(label, index) == index else f"@{index}"
            check("help-version/" + label, "commands", self.help_case, case, needs=[f"help_version.cases.{index}"] if index is not None else [])
        for name in dict.fromkeys([*sorted(CONTRACTS), *probes]):
            if name not in probes and not any(p in {"probes", "probes." + name, "inapplicable", "inapplicable." + name} for p, _ in problems):
                continue
            contract = CONTRACTS.get(name, {})
            method = contract.get("method", "probe")
            check(method + "/" + name, "work" if method == "retry" else "output", getattr(self, method), name)
            if contract.get("stable"):
                check("stable-error/" + name, "output", self.stable_error, name)
            if "also" in contract:
                rule, method, args = contract["also"]
                check(rule, "work", getattr(self, method), *args)
            if contract.get("interaction"):
                for index, (tty, flags) in enumerate(FLAG_CASES[contract["interaction"]] + (FLAG_CASES["tty"] if os.name == "posix" else [])):
                    check(f"interaction/{name}/{index}", "output", self.interaction, name, flags, tty)
        tree = self.manifest.get("command_tree", [])
        for command, (name, spec) in self.command_cases().items():
            needs = ["flag_probes." + command] + ([f"command_tree.{i}" for i, c in enumerate(tree) if c == command or command == f"@{i}"] if isinstance(tree, list) else ["command_tree"])
            for flag, before in FLAG_CASES["shared"]:
                side = "before" if before else "after"
                rule = f"flag/{command}/{flag}/{side}"
                check(rule, "commands", self.flag, flag, before, name, spec, needs=needs)
            if os.name == "posix":
                check("json/color-capable-tty/" + command, "output", self.json_terminal, name, spec, needs=needs)
        for index, alias in enumerate(self.manifest.get("aliases", []) if isinstance(self.manifest.get("aliases"), list) else [None]):
            for quiet in (False, True):
                rule = f"alias/{index}/{quiet}"
                check(rule, "commands", self.alias, alias, quiet)
        return self.results
    # fmt: on


def lookup(value: Any, path: str) -> Any:
    for part in path.split("."):
        value = value[part]
    return value


def check_manifest(path: Path) -> list:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    root = Path(os.environ.get("MATILDA_ARTIFACT_ROOT", tempfile.gettempdir()))
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="goobits-conformance-", dir=root) as state:
        return Suite(manifest, path.resolve().parent, state).execute()
