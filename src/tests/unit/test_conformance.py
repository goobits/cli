"""Exercise every reported rule against real conforming and broken subprocesses."""

import copy
import json
import sys
from pathlib import Path

import pytest

from goobits_cli.commands.conformance import run_cli
from goobits_cli.conformance.suite import (
    CODES,
    SCENARIOS,
    Suite,
    check_manifest,
    documents,
    envelope_errors,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "conformance"


def manifest(broken=False):
    value = json.loads(
        (FIXTURES.parents[3] / "docs" / "conformance.example.json").read_text()
    )
    value["executable"] = [
        sys.executable,
        str(FIXTURES / ("broken.py" if broken else "conforming.py")),
    ]
    value["fixture"]["argv"] = [
        sys.executable,
        str(FIXTURES / "conforming.py"),
        "fixture",
    ]
    return value


def write_manifest(tmp_path, value):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(value))
    return path


def test_every_rule_accepts_conforming_and_rejects_broken(tmp_path):
    good = check_manifest(write_manifest(tmp_path, manifest()))
    assert good and all(c["passed"] for c in good), [c for c in good if not c["passed"]]
    bad = check_manifest(write_manifest(tmp_path, manifest(True)))
    assert [c["rule"] for c in good] == [c["rule"] for c in bad]
    assert all(not c["passed"] for c in bad if c["rule"] != "manifest")
    assert all(
        c["section"].startswith("docs/cli-standard.md#") and c["fix_hint"] for c in good
    )


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_manifest_cannot_omit_required_scenario(tmp_path, scenario):
    value = manifest()
    del value["probes"][scenario]
    problems = Suite(value, tmp_path, str(tmp_path)).validate_manifest(collect=True)
    assert any(path == "probes." + scenario for path, _ in problems)


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("command", 1),
        ("ok", 1),
        ("data", "MISSING"),
        ("errors", None),
        ("request_id", ""),
        ("status", "running"),
    ],
)
def test_envelope_types(key, value):
    doc = {
        "schema_version": 1,
        "command": "tiny item read",
        "ok": True,
        "data": None,
        "errors": [],
        "request_id": "local",
        "status": "completed",
    }
    if value == "MISSING":
        del doc[key]
    else:
        doc[key] = value
    assert envelope_errors(doc)


@pytest.mark.parametrize(
    "key,value",
    [
        ("code", ""),
        ("message", None),
        ("retryable", 1),
        ("next_action", ""),
        ("target", 1),
    ],
)
def test_error_types(key, value):
    error = {
        "code": "stable",
        "message": "failure",
        "retryable": False,
        "next_action": "inspect",
        "target": None,
    }
    error[key] = value
    doc = {
        "schema_version": 1,
        "command": "tiny item read",
        "ok": False,
        "data": None,
        "errors": [error],
        "request_id": "local",
        "status": "failed",
    }
    assert envelope_errors(doc)


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["check"],
        ["check", "--unknown"],
        ["check", "--manifest", "/missing"],
        ["check", "--quiet", "--verbose"],
    ],
)
def test_own_parser_errors_are_envelopes(argv, capsys):
    assert run_cli(["conformance"] + argv + ["--json"]) == 2
    assert documents(capsys.readouterr().out)[0]["status"] == "failed"


@pytest.mark.parametrize("broken,exit_code", [(False, 0), (True, 3)])
def test_own_check_receipt(tmp_path, capsys, broken, exit_code):
    path = write_manifest(tmp_path, manifest(broken))
    assert (
        run_cli(["--json", "conformance", "check", "--manifest", str(path)])
        == exit_code
    )
    doc = documents(capsys.readouterr().out)[0]
    assert doc["ok"] == (exit_code == 0)


@pytest.mark.parametrize(
    "defect,method,args",
    [
        (
            "help",
            "help_case",
            ({"argv": ["--help"], "kind": "text", "json": False, "command": "tiny"},),
        ),
        ("envelope", "probe", ("read",)),
        ("canonical", "probe", ("read",)),
        ("exit", "probe", ("read",)),
        ("stdout", "probe", ("read",)),
        ("quiet", "flag", ("--quiet", True)),
        ("verbose", "flag", ("--verbose", False)),
        ("request", "probe", ("unavailable",)),
        ("prompt", "interaction", ("confirmation", ["--no-input"])),
        ("effects", "interaction", ("missing-input", [])),
        ("acceptance", "probe", ("acceptance",)),
        ("completion", "probe", ("completion",)),
        ("dedup", "retry", ("mutation",)),
        ("conflict", "retry", ("mutation",)),
        ("receipt", "receipts", ()),
        ("expiry", "probe", ("expiry",)),
        ("unknown", "probe", ("unknown-fields",)),
        ("alias", "alias", (None,)),
    ],
)
def test_individual_defects_do_not_hide_behind_invalid_json(
    tmp_path, defect, method, args
):
    value = manifest(True)
    value["fixture"]["env"] = {"GOOBITS_BREAK": defect}
    if method == "alias":
        args = (value["aliases"][0],)
    suite = Suite(value, tmp_path, str(tmp_path))
    suite.check(
        defect, "output", lambda: getattr(suite, method)(*args), "fix the defect"
    )
    assert not suite.results[0]["passed"], suite.results


@pytest.mark.parametrize("suffix", ["\n\n", "\nextra", ""])
def test_machine_output_requires_one_final_newline(suffix):
    doc = {
        "schema_version": 1,
        "command": "tiny item read",
        "ok": True,
        "data": None,
        "errors": [],
        "request_id": "local",
        "status": "completed",
    }
    with pytest.raises((ValueError, AssertionError)):
        documents(json.dumps(doc) + suffix)


def test_documented_existing_envelope_mapping():
    mapping = {
        "documentation": "docs/native-contract.md",
        "versions": ["v2"],
        "fields": {
            key: key
            for key in (
                "schema_version",
                "command",
                "ok",
                "data",
                "errors",
                "request_id",
                "status",
            )
        },
        "error_fields": {
            key: key
            for key in ("code", "message", "retryable", "next_action", "target")
        },
        "statuses": {"done": "completed"},
    }
    doc = {
        "schema_version": "v2",
        "command": "tiny item read",
        "ok": True,
        "data": None,
        "errors": [],
        "request_id": "local",
        "status": "done",
        "optional_future_field": 123,
    }
    assert (
        documents(json.dumps(doc) + "\n", mapping=mapping)[0]["status"] == "completed"
    )
    doc["schema_version"] = "v3"
    with pytest.raises(AssertionError, match="unsupported"):
        documents(json.dumps(doc) + "\n", mapping=mapping)


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["--json", "conformance", "check", "--manifest", "/missing"], 2),
        (["conformance", "check", "--json", "--help", "--quiet", "--verbose"], 0),
        (["conformance", "check", "--version", "--json"], 0),
    ],
)
def test_installed_entrypoint_machine_contract(argv, expected):
    import os
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "goobits_cli.main"] + argv,
        capture_output=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        timeout=10,
    )
    assert result.returncode == expected, result.stderr
    doc = documents(result.stdout)[0]
    assert doc["command"] == "goobits conformance check"


@pytest.mark.parametrize("explicit_root", [False, True])
def test_state_uses_writable_temporary_directory(tmp_path, monkeypatch, explicit_root):
    """An empty environment must not require a writable host artifact directory."""
    import tempfile

    from goobits_cli.conformance import suite

    monkeypatch.delenv("MATILDA_ARTIFACT_ROOT", raising=False)
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    root = tmp_path / "artifacts" if explicit_root else tmp_path
    if explicit_root:
        monkeypatch.setenv("MATILDA_ARTIFACT_ROOT", str(root))
    original = tempfile.TemporaryDirectory

    def temporary_directory(*args, **kwargs):
        assert Path(kwargs["dir"]) == root
        return original(*args, **kwargs)

    monkeypatch.setattr(tempfile, "TemporaryDirectory", temporary_directory)
    monkeypatch.setattr(suite.Suite, "execute", lambda self: [])
    assert check_manifest(write_manifest(tmp_path, manifest())) == []
