"""Regressions from the review of 037121a; each was red before its fix."""

import json

import pytest

from goobits_cli.commands.conformance import run_cli
from goobits_cli.conformance.suite import Suite, documents

from .test_conformance import manifest


def target(tmp_path, defect=None):
    value = manifest(bool(defect))
    if defect:
        value["fixture"]["env"] = {"GOOBITS_BREAK": defect}
    return Suite(value, tmp_path, str(tmp_path))


@pytest.mark.parametrize(
    "scenario",
    ["unknown-fields", "unknown-version", "expiry", "mutation", "acceptance"],
)
def test_faults_have_backend_evidence(tmp_path, scenario):
    suite = target(tmp_path)
    suite.fixture("reset", scenario)
    if scenario in {"mutation", "acceptance"}:
        suite.run(
            suite.manifest["probes"][scenario]["argv"]
            + (["--idempotency-key", "test"] if scenario == "mutation" else [])
        )
    else:
        suite.run(suite.manifest["probes"][scenario]["argv"])
    state = suite.fixture("inspect", scenario)
    if scenario.startswith("unknown"):
        assert state["upstream_messages"]
        assert state["upstream_messages"][-1]["schema_version"] == (
            999 if scenario == "unknown-version" else 1
        )
        if scenario == "unknown-fields":
            assert "future_optional" in state["upstream_messages"][-1]
    elif scenario == "expiry":
        assert (
            state["expired_entries"]
            and state["clock"] > state["expired_entries"][0]["expires_at"]
        )
    else:
        assert state["operations"] and state["ledger"]
        assert state["postcondition"] == (scenario == "mutation")
        assert state["effects"] == len(state["effects_log"])


@pytest.mark.parametrize(
    "case_id",
    [
        "root-help",
        "root-help-command",
        "leaf-help",
        "root-version",
        "help-missing-input",
        "version-missing-input",
        "text-conflict",
        "version-conflict",
        "json-help-before",
        "json-help-after",
        "json-version-before",
        "json-version-after",
        "help-version",
        "version-help",
    ],
)
def test_required_eager_cases_cannot_be_omitted(tmp_path, case_id):
    suite = target(tmp_path)
    suite.manifest["help_version"]["cases"] = [
        c for c in suite.manifest["help_version"]["cases"] if c.get("id") != case_id
    ]
    with pytest.raises((AssertionError, KeyError), match="case|matrix"):
        suite.validate_manifest()


def test_flags_cover_stream_failure_and_inspection_paths(tmp_path, monkeypatch):
    suite = target(tmp_path)
    suite.manifest["probes"]["stream"]["command"] = "tiny item stream"
    suite.manifest["probes"]["unavailable"]["command"] = "tiny item fail"
    suite.manifest["command_tree"] += ["tiny item stream", "tiny item fail"]
    seen = set()
    for method in (
        "validate_manifest",
        "help_case",
        "probe",
        "stable_error",
        "generated_key",
        "interaction",
        "alias",
        "retry",
        "receipts",
    ):
        monkeypatch.setattr(suite, method, lambda *a, **kw: None)

    def flag(_flag, _before, name="read", spec=None):
        seen.add((spec or suite.manifest["probes"][name])["command"])

    monkeypatch.setattr(suite, "flag", flag)
    suite.execute()
    assert set(suite.manifest["command_tree"]) <= seen


def test_verbose_cannot_change_result(tmp_path):
    suite = target(tmp_path, "verbose-result")
    with pytest.raises(AssertionError, match="result|stdout"):
        suite.flag("--verbose", True)


def test_help_keywords_are_not_documentation(tmp_path):
    suite = target(tmp_path, "help-keywords")
    case = next(
        c for c in suite.manifest["help_version"]["cases"] if c["kind"] == "text"
    )
    with pytest.raises(AssertionError, match="help|documentation"):
        suite.help_case(case)


def test_local_validation_needs_no_backend_dispatch(tmp_path, monkeypatch):
    suite = target(tmp_path, "local-validation")
    inspect = suite.fixture

    def fixture(action, scenario="read"):
        state = inspect(action, scenario)
        state["request_ids"] = []
        return state

    monkeypatch.setattr(suite, "fixture", fixture)
    suite.probe("invalid-input")
    assert suite.fixture("inspect")["service_calls"] == 0


def test_quiet_keeps_a_required_warning(tmp_path, monkeypatch):
    suite = target(tmp_path, "quiet-warning")
    suite.manifest["diagnostics"] = {
        "deprecation": ["^deprecated: old option; use --value$"]
    }
    execute = suite.run

    def run(argv, hook=False, request=None):
        result = execute(argv, hook, request)
        if not hook and "--quiet" in argv:
            result.stderr += "deprecated: old option; use --value\n"
        return result

    monkeypatch.setattr(suite, "run", run)
    suite.flag("--quiet", False)


def test_accepted_then_completed_stream_is_valid():
    doc = {
        "schema_version": 1,
        "command": "tiny item stream",
        "ok": True,
        "data": None,
        "errors": [],
        "request_id": "request",
        "status": "accepted",
    }
    text = json.dumps(doc) + "\n" + json.dumps(dict(doc, status="completed")) + "\n"
    assert len(documents(text, stream=True)) == 2


@pytest.mark.parametrize(
    "method,args",
    [("interaction", ("confirmation", ["--json"])), ("retry", ("mutation",))],
)
def test_legacy_exit_mappings_apply_everywhere(tmp_path, method, args, monkeypatch):
    suite = target(tmp_path, "legacy-exits")
    suite.manifest["legacy_exits"] = {"22": 2, "44": 4}
    execute = suite.run

    def run(argv, hook=False, request=None):
        result = execute(argv, hook, request)
        if not hook:
            result.returncode = {2: 22, 4: 44}.get(result.returncode, result.returncode)
        return result

    monkeypatch.setattr(suite, "run", run)
    getattr(suite, method)(*args)


@pytest.mark.parametrize(
    "args,command",
    [
        (["conformance"], "goobits conformance"),
        (["conformance", "unknown"], "goobits conformance"),
        (["conformance", "check", "--bad"], "goobits conformance check"),
    ],
)
def test_parser_reports_only_resolved_path(args, command, capsys):
    assert run_cli(args + ["--json"]) == 2
    assert documents(capsys.readouterr().out)[0]["command"] == command


@pytest.mark.skipif(__import__("os").name != "posix", reason="PTY requires POSIX")
def test_json_disables_color_without_environment_help(tmp_path, monkeypatch):
    import subprocess

    suite = target(tmp_path)
    popen = subprocess.Popen

    def launch(*args, **kwargs):
        assert "NO_COLOR" not in kwargs["env"]
        assert kwargs["env"]["TERM"] != "dumb"
        return popen(*args, **kwargs)

    suite.fixture("reset", "read")
    monkeypatch.setattr(subprocess, "Popen", launch)
    result = suite.terminal_run(["item", "read", "--json"], "both")
    assert "\x1b" not in result.stdout


@pytest.mark.parametrize(
    "defect,scenario",
    [
        ("reader-fields", "unknown-fields"),
        ("reader-version", "unknown-version"),
        ("completion", "completion"),
    ],
)
def test_real_reader_and_postcondition_defects(tmp_path, defect, scenario):
    suite = target(tmp_path, defect)
    suite.check(defect, "work", lambda: suite.probe(scenario), "fix reader/state")
    assert not suite.results[0]["passed"]


@pytest.mark.parametrize(
    "case_id,defect",
    [
        ("root-help-command", "root-scope"),
        ("help-missing-input", "help-missing"),
        ("version-missing-input", "help-missing"),
        ("json-help-after", "json-eager"),
        ("json-version-after", "json-eager"),
    ],
)
def test_native_eager_defects_are_independently_detected(tmp_path, case_id, defect):
    suite = target(tmp_path, defect)
    case = next(
        c for c in suite.manifest["help_version"]["cases"] if c["id"] == case_id
    )
    suite.check(case_id, "commands", lambda: suite.help_case(case), "fix eager parsing")
    assert not suite.results[0]["passed"]


@pytest.mark.parametrize(
    "topic",
    [
        "defaults",
        "examples",
        "configuration precedence",
        "exit codes",
        "simultaneous failures",
        "scope",
        "retention",
        "schema",
        "mapping",
    ],
)
def test_concrete_documentation_passages_cannot_be_removed(tmp_path, topic):
    suite = target(tmp_path, "help-doc/" + topic)
    case = next(
        c for c in suite.manifest["help_version"]["cases"] if c["kind"] == "text"
    )
    with pytest.raises(AssertionError, match="help documentation"):
        suite.help_case(case)


def test_expiry_changes_real_deduplication_and_scope_is_respected(tmp_path):
    suite = target(tmp_path)
    state = suite.fixture("reset", "expiry")
    original = state["operation_id"]
    result = suite.run(["item", "write", "--json", "--idempotency-key", "expired-key"])
    assert result.returncode == 0
    assert documents(result.stdout)[0]["data"]["operation_id"] != original
    assert suite.fixture("inspect")["effects"] == 2
    suite.run(
        [
            "item",
            "write",
            "--json",
            "--scope",
            "other",
            "--idempotency-key",
            "expired-key",
        ]
    )
    state = suite.fixture("inspect")
    assert state["effects"] == 3 and len(state["ledger"]) == 2
    assert state["resources"]["other"] == "value"


@pytest.mark.skipif(__import__("os").name != "posix", reason="PTY requires POSIX")
def test_color_defect_cannot_hide_behind_no_color_environment(tmp_path):
    suite = target(tmp_path, "json-color")
    suite.check("color", "output", suite.json_terminal, "disable color in JSON mode")
    assert not suite.results[0]["passed"]


@pytest.mark.heavy
@pytest.mark.parametrize("language", ["rust", "typescript"])
def test_native_pilot_manifest(tmp_path, language):
    import shutil
    import subprocess

    from goobits_cli.conformance.suite import check_manifest

    from .test_conformance import FIXTURES, write_manifest

    pilots = FIXTURES / "pilots"
    compiler = "rustc" if language == "rust" else "tsc"
    assert shutil.which(compiler), compiler + " is required for the native pilot"
    if language == "rust":
        output = tmp_path / "rust-pilot"
        subprocess.run(
            [compiler, str(pilots / "rust.rs"), "-o", str(output)],
            check=True,
            timeout=60,
            capture_output=True,
        )
        executable = [str(output)]
    else:
        subprocess.run(
            [
                compiler,
                str(pilots / "typescript.ts"),
                "--target",
                "es2020",
                "--outDir",
                str(tmp_path),
            ],
            check=True,
            timeout=60,
            capture_output=True,
        )
        executable = ["node", str(tmp_path / "typescript.js")]
    value = json.loads((pilots / (language + ".manifest.json")).read_text())
    value["executable"] = executable
    value["fixture"]["argv"] = [
        __import__("sys").executable,
        str(pilots / "fixture.py"),
    ]
    value["fixture"]["env"]["PILOT_HELP"] = str(pilots / "help.txt")
    results = check_manifest(write_manifest(tmp_path, value))
    assert all(c["passed"] for c in results), [c for c in results if not c["passed"]]


def test_quiet_keeps_errors_on_failure_only_path(tmp_path):
    suite = target(tmp_path, "quiet-error")
    suite.flag("--quiet", True, "unavailable")
