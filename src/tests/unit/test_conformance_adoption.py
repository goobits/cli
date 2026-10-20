"""Manifest diagnostics and incremental adoption regressions."""

import json
import subprocess
import sys

import pytest

from goobits_cli.conformance.suite import Suite

from .test_conformance import FIXTURES, manifest


def test_manifest_reports_all_problems_and_runs_independent_checks(
    tmp_path, monkeypatch, capsys
):
    value = manifest()
    del value["probes"]["mutation"]["equivalent_argv"]
    del value["probes"]["unknown-version"]["error_codes"]
    del value["help_required"]["defaults"]
    suite = Suite(value, tmp_path, str(tmp_path))
    results = suite.execute()
    failures = [r for r in results if r["passed"] is False]
    assert any("equivalent_argv" in r["detail"] for r in failures)
    assert any("error_codes" in r["detail"] for r in failures)
    assert any("defaults" in r["detail"] for r in failures)
    assert next(r for r in results if r["rule"] == "probe/read")["passed"]
    skipped = next(r for r in results if r["rule"] == "retry/mutation")
    assert skipped["skipped"] and "equivalent_argv" in skipped["detail"]
    assert next(r for r in results if r["rule"] == "generated-retry-key")["passed"]
    from goobits_cli.commands import conformance

    monkeypatch.setattr(conformance, "check_manifest", lambda path: results)
    assert (
        conformance.run_cli(["conformance", "check", "--manifest", "unused", "--json"])
        == 3
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["data"]["checks"] == results


def butter_manifest(tmp_path):
    """A read-only pilot with only legacy 0/1 exits and documented adoption."""
    import shutil

    pilots = FIXTURES / "pilots"
    for name in ("portable.py", "fixture.py", "help.txt"):
        shutil.copyfile(pilots / name, tmp_path / name)
    value = json.loads((pilots / "typescript.manifest.json").read_text())
    value["executable"] = [sys.executable, str(tmp_path / "portable.py"), "legacy"]
    value["fixture"]["argv"] = [sys.executable, str(tmp_path / "fixture.py")]
    value["fixture"]["env"]["PILOT_HELP"] = str(tmp_path / "help.txt")
    value["legacy_exits"] = {"1": 2}
    value["help_required"]["exit codes"] = (
        "Exit codes: 0 success; 1 any handled failure maps to category 2; deprecated. "
        "Use pilot --canonical-exits item read."
    )
    help_path = tmp_path / "help.txt"
    text = help_path.read_text()
    old = next(line for line in text.splitlines() if line.startswith("Exit codes:"))
    help_path.write_text(text.replace(old, value["help_required"]["exit codes"]))
    return value


def test_legacy_zero_one_manifest_is_deprecated_not_failed(
    tmp_path, monkeypatch, capsys
):
    suite = Suite(butter_manifest(tmp_path), tmp_path, str(tmp_path))
    results = suite.execute()
    assert all(r["passed"] for r in results), [r for r in results if not r["passed"]]
    assert any(r.get("warning") and "deprecated" in r["detail"] for r in results)
    from goobits_cli.commands import conformance

    monkeypatch.setattr(conformance, "check_manifest", lambda path: results)
    assert (
        conformance.run_cli(
            ["conformance", "check", "--manifest", "unused", "--json", "--quiet"]
        )
        == 0
    )
    output = capsys.readouterr()
    assert json.loads(output.out)["ok"]
    assert output.err.count("deprecated") == 1


def test_legacy_one_still_cannot_report_success(tmp_path):
    suite = Suite(butter_manifest(tmp_path), tmp_path, str(tmp_path))
    with pytest.raises(AssertionError):
        suite.category(subprocess.CompletedProcess([], 1), expected=0)


def test_unmapped_one_is_still_a_crash(tmp_path):
    suite = Suite(manifest(), tmp_path, str(tmp_path))
    with pytest.raises(AssertionError, match="reserved|crash"):
        suite.category(subprocess.CompletedProcess([], 1))


@pytest.mark.parametrize(
    "field,value",
    [
        ("probes", None),
        ("fixture", None),
        ("help_version", None),
        ("command_tree", 7),
        ("aliases", None),
        ("payload_schema", None),
    ],
)
def test_bad_sections_do_not_abort_reporting(tmp_path, monkeypatch, field, value):
    spec = manifest()
    spec[field] = value
    suite = Suite(spec, tmp_path, str(tmp_path))
    for name in (
        "probe",
        "help_case",
        "flag",
        "retry",
        "alias",
        "receipts",
        "interaction",
        "json_terminal",
        "stable_error",
    ):
        monkeypatch.setattr(suite, name, lambda *a, **kw: None)
    results = suite.execute()
    assert any(
        r["rule"] == "manifest/" + field and r["passed"] is False for r in results
    )
    assert any(r.get("skipped") for r in results) or field == "aliases"


def test_malformed_probe_does_not_block_other_paths(tmp_path, monkeypatch):
    value = manifest()
    value["probes"]["read"] = None
    suite = Suite(value, tmp_path, str(tmp_path))
    for name in (
        "probe",
        "help_case",
        "flag",
        "retry",
        "alias",
        "receipts",
        "interaction",
        "json_terminal",
        "stable_error",
    ):
        monkeypatch.setattr(suite, name, lambda *a, **kw: None)
    results = suite.execute()
    assert next(r for r in results if r["rule"] == "probe/read")["skipped"]
    assert next(r for r in results if r["rule"] == "probe/completion")["passed"]


@pytest.mark.parametrize("category", [2, 3, 4, 5, 124, 130])
def test_declared_lossy_exit_covers_handled_failure_categories(tmp_path, category):
    suite = Suite(butter_manifest(tmp_path), tmp_path, str(tmp_path))
    assert suite.category(subprocess.CompletedProcess([], 1), category) == category


def test_legacy_adoption_requires_mapping_in_real_help(tmp_path):
    value = butter_manifest(tmp_path)
    path = tmp_path / "help.txt"
    path.write_text(
        path.read_text().replace("Use pilot --canonical-exits item read.", "")
    )
    suite = Suite(value, tmp_path, str(tmp_path))
    with pytest.raises(AssertionError):
        suite.help_case(value["help_version"]["cases"][0])


def test_schema_forbids_success_mapping_for_exit_one(tmp_path):
    import jsonschema

    schema = json.loads(
        (FIXTURES.parents[3] / "docs/conformance-manifest.schema.json").read_text()
    )
    value = butter_manifest(tmp_path)
    value["legacy_exits"]["1"] = 0
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(value, schema)
    with pytest.raises(AssertionError, match="legacy_exits"):
        Suite(value, tmp_path, str(tmp_path)).validate_manifest()


@pytest.mark.parametrize("part", ["case-id", "flag-probe"])
def test_bad_identifiers_cannot_abort_scheduling(tmp_path, monkeypatch, part):
    value = manifest()
    if part == "case-id":
        value["help_version"]["cases"][0]["id"] = []
    else:
        value["flag_probes"]["tiny item read"] = []
    suite = Suite(value, tmp_path, str(tmp_path))
    for name in (
        "probe",
        "help_case",
        "flag",
        "retry",
        "alias",
        "receipts",
        "interaction",
        "json_terminal",
        "stable_error",
    ):
        monkeypatch.setattr(suite, name, lambda *a, **kw: None)
    results = suite.execute()
    rule = (
        "help-version/root-help"
        if part == "case-id"
        else "flag/tiny item read/--json/before"
    )
    assert next(r for r in results if r["rule"] == rule)["skipped"]


def test_missing_version_keeps_text_help_independent(tmp_path, monkeypatch):
    value = manifest()
    del value["version"]
    suite = Suite(value, tmp_path, str(tmp_path))
    for name in (
        "probe",
        "help_case",
        "flag",
        "retry",
        "alias",
        "receipts",
        "interaction",
        "json_terminal",
        "stable_error",
    ):
        monkeypatch.setattr(suite, name, lambda *a, **kw: None)
    results = suite.execute()
    assert next(r for r in results if r["rule"] == "help-version/root-help")["passed"]
    assert next(r for r in results if r["rule"] == "help-version/root-version")[
        "skipped"
    ]


def test_each_bad_long_flag_gets_its_own_problem(tmp_path):
    value = manifest()
    value["long_flags"] = ["--camelCase", "--snake_case"]
    paths = {
        path
        for path, _ in Suite(value, tmp_path, str(tmp_path)).validate_manifest(
            collect=True
        )
    }
    assert {"long_flags.0", "long_flags.1"} <= paths


def test_bad_canonical_entry_keeps_other_paths_independent(tmp_path, monkeypatch):
    value = manifest()
    value["command_tree"].append("tiny invalid_name read")
    suite = Suite(value, tmp_path, str(tmp_path))
    for name in (
        "probe",
        "help_case",
        "flag",
        "retry",
        "alias",
        "receipts",
        "interaction",
        "json_terminal",
        "stable_error",
    ):
        monkeypatch.setattr(suite, name, lambda *a, **kw: None)
    results = suite.execute()
    assert any(r["rule"].startswith("manifest/command_tree.") for r in results)
    assert next(r for r in results if r["rule"] == "probe/read")["passed"]
