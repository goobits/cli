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


@pytest.mark.parametrize("language", ["rust", "typescript"])
def test_pilot_manifest_without_native_toolchain(tmp_path, language, monkeypatch):
    import shutil
    import sys

    from goobits_cli.conformance.suite import check_manifest

    from .test_conformance import FIXTURES, write_manifest

    # Both native parsing policies run under the declared Python dependency.
    # Child processes use only copied assets and their private state directory.
    pilots = FIXTURES / "pilots"
    for name in ("portable.py", "fixture.py", "help.txt"):
        shutil.copyfile(pilots / name, tmp_path / name)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.delenv("MATILDA_ARTIFACT_ROOT", raising=False)
    value = json.loads((pilots / (language + ".manifest.json")).read_text())
    value["executable"] = [sys.executable, str(tmp_path / "portable.py"), language]
    value["fixture"]["argv"] = [sys.executable, str(tmp_path / "fixture.py")]
    value["fixture"]["env"]["PILOT_HELP"] = str(tmp_path / "help.txt")
    results = check_manifest(write_manifest(tmp_path, value))
    assert all(c["passed"] for c in results), [c for c in results if not c["passed"]]


def test_quiet_keeps_errors_on_failure_only_path(tmp_path):
    suite = target(tmp_path, "quiet-error")
    suite.flag("--quiet", True, "unavailable")


@pytest.mark.parametrize(
    "flag", ["--json", "--quiet", "--verbose", "--yes", "--no-input"]
)
@pytest.mark.parametrize("before", [True, False])
def test_shared_flags_preserve_required_confirmation(
    tmp_path, flag, before, monkeypatch
):
    suite = target(tmp_path)
    spec = suite.manifest["probes"]["confirmation-yes"]
    spec["argv"].append("--no-input")
    execute = suite.run

    def run(argv, hook=False, request=None):
        if not hook:
            assert "--yes" in argv and "--no-input" in argv
        return execute(argv, hook, request)

    monkeypatch.setattr(suite, "run", run)
    suite.flag(flag, before, "confirmation-yes", spec)
    assert suite.fixture("inspect")["effects"] == 1


@pytest.mark.parametrize("before", [True, False])
def test_yes_uses_declared_confirmation_outcome(tmp_path, before):
    suite = target(tmp_path)
    suite.flag("--yes", before, "confirmation")
    assert suite.fixture("inspect")["effects"] == 1


def test_dispatch_false_cannot_hide_observed_forwarding(tmp_path):
    suite = target(tmp_path, "request")
    suite.manifest["probes"]["read"]["dispatch"] = False
    with pytest.raises(AssertionError, match="request ID was not forwarded"):
        suite.probe("read")


@pytest.mark.parametrize(
    "method,name,mapped", [("retry", "mutation", 2), ("interaction", "confirmation", 4)]
)
def test_reserved_exit_one_cannot_become_a_legacy_category(
    tmp_path, monkeypatch, method, name, mapped
):
    suite = target(tmp_path)
    suite.manifest["legacy_exits"] = {"1": mapped}
    execute = suite.run

    def run(argv, hook=False, request=None):
        result = execute(argv, hook, request)
        if not hook and (method == "interaction" or "--changed" in argv):
            result.returncode = 1
        return result

    monkeypatch.setattr(suite, "run", run)
    args = (name,) if method == "retry" else (name, ["--json"])
    with pytest.raises(AssertionError, match="reserved|crash"):
        getattr(suite, method)(*args)


def test_manifest_rejects_reserved_exit_mapping(tmp_path):
    suite = target(tmp_path)
    suite.manifest["legacy_exits"] = {"1": 2}
    with pytest.raises(AssertionError, match="reserved|crash"):
        suite.validate_manifest()


def test_schema_rejects_reserved_exit_mapping():
    import jsonschema

    from .test_conformance import FIXTURES

    schema = json.loads(
        (FIXTURES.parents[3] / "docs/conformance-manifest.schema.json").read_text()
    )
    value = manifest()
    value["legacy_exits"] = {"1": 2}
    value["canonical_exit_invocation"] = "tiny --canonical-exits item read"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, schema)


@pytest.mark.parametrize(
    "missing", ["retry", "confirmation-yes", "canonical_exit_invocation"]
)
def test_schema_requires_conditional_declarations(missing):
    import jsonschema

    from .test_conformance import FIXTURES

    schema = json.loads(
        (FIXTURES.parents[3] / "docs/conformance-manifest.schema.json").read_text()
    )
    value = manifest()
    if missing == "confirmation-yes":
        del value["probes"][missing]
    elif missing == "canonical_exit_invocation":
        value["legacy_exits"] = {"22": 2}
    else:
        del value[missing]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, schema)


@pytest.mark.parametrize(
    "original,selected", [("--verbose", "--quiet"), ("--quiet", "--verbose")]
)
def test_flag_selection_replaces_competing_diagnostic_mode(
    tmp_path, original, selected
):
    suite = target(tmp_path)
    suite.manifest["probes"]["read"]["argv"].append(original)
    suite.flag(selected, True)


@pytest.mark.parametrize(
    "relative",
    [
        "docs/conformance.example.json",
        "src/tests/fixtures/conformance/pilots/rust.manifest.json",
        "src/tests/fixtures/conformance/pilots/typescript.manifest.json",
    ],
)
def test_published_manifests_validate_against_schema(relative):
    import jsonschema

    from .test_conformance import FIXTURES

    root = FIXTURES.parents[3]
    schema = json.loads((root / "docs/conformance-manifest.schema.json").read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.validate(json.loads((root / relative).read_text()), schema)


def test_runner_stays_within_reviewed_line_bound():
    from .test_conformance import FIXTURES

    source = FIXTURES.parents[3] / "src/goobits_cli/conformance/suite.py"
    assert len(source.read_text().splitlines()) <= 732
