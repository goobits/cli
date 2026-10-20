"""Regressions for declarations that were lost or executed after validation failed."""

import copy

import pytest

from goobits_cli.conformance.suite import Suite

from .test_conformance import manifest


@pytest.fixture
def plan(tmp_path, monkeypatch):
    suite = Suite(manifest(), tmp_path, str(tmp_path))
    calls = []
    for method in (
        "help_case",
        "probe",
        "flag",
        "json_terminal",
        "interaction",
        "alias",
        "stable_error",
        "retry",
        "receipts",
    ):
        monkeypatch.setattr(
            suite, method, lambda *args, method=method: calls.append((method, args))
        )
    return suite, calls


def row(results, rule):
    return next(r for r in results if r["rule"] == rule)


@pytest.mark.parametrize(
    "extra",
    [
        None,
        {},
        {"argv": ["--help"], "kind": "text", "json": False, "command": "tiny"},
        {
            "id": [],
            "argv": ["--help"],
            "kind": "text",
            "json": False,
            "command": "tiny",
        },
        {
            "id": "extra",
            "argv": "--help",
            "kind": "text",
            "json": False,
            "command": "tiny",
        },
        {
            "id": "extra",
            "argv": ["--help"],
            "kind": "text",
            "json": "yes",
            "command": "tiny",
        },
    ],
)
def test_every_malformed_extra_help_case_is_reported_and_skipped(plan, extra):
    suite, calls = plan
    index = len(suite.manifest["help_version"]["cases"])
    suite.manifest["help_version"]["cases"].append(extra)
    results = suite.execute()
    path = f"help_version.cases.{index}"
    assert any(
        r["rule"].startswith("manifest/" + path) and r["passed"] is False
        for r in results
    )
    assert any(r.get("skipped") and path in r["detail"] for r in results)
    assert row(results, "help-version/root-help")["passed"]
    assert not any(method == "help_case" and args[0] is extra for method, args in calls)


def test_duplicate_help_ids_are_reported_without_replacing_the_original(plan):
    suite, calls = plan
    duplicate = copy.deepcopy(suite.manifest["help_version"]["cases"][0])
    suite.manifest["help_version"]["cases"].append(duplicate)
    results = suite.execute()
    assert any(r["rule"].startswith("manifest/help_version.cases.14") for r in results)
    assert row(results, "help-version/root-help")["passed"]
    assert not any(
        method == "help_case" and args[0] is duplicate for method, args in calls
    )


@pytest.mark.parametrize(
    "path,value",
    [
        ("timeout_seconds", "bad"),
        ("timeout_seconds", 0),
        ("timeout_seconds", True),
        ("fixture.env", []),
        ("fixture.env.BAD", 7),
        ("envelope_mapping", False),
        ("envelope_mapping.fields", []),
    ],
)
def test_schema_invalid_execution_settings_block_dependent_checks(plan, path, value):
    suite, calls = plan
    parts = path.split(".")
    target = suite.manifest
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value
    results = suite.execute()
    assert any(r["rule"].startswith("manifest/" + path) for r in results)
    read = row(results, "probe/read")
    assert read["skipped"] and path in read["detail"]
    assert not any(method == "probe" and args[0] == "read" for method, args in calls)


@pytest.mark.parametrize(
    "path,value",
    [
        ("diagnostics.error", "bad"),
        ("diagnostics.error", ["["]),
        ("volatile_paths", [7]),
    ],
)
def test_flag_settings_block_only_the_flags_that_read_them(plan, path, value):
    suite, calls = plan
    if "." in path:
        parent, key = path.split(".")
        suite.manifest.setdefault(parent, {})[key] = value
    else:
        suite.manifest[path] = value
    results = suite.execute()
    assert any(r["rule"].startswith("manifest/" + path) for r in results)
    quiet = row(results, "flag/tiny item read/--quiet/before")
    assert quiet["skipped"] and path in quiet["detail"]
    assert row(results, "probe/read")["passed"]


def test_receipts_skip_before_acceptance_runs_when_inspection_argv_is_missing(
    plan, monkeypatch
):
    suite, calls = plan
    del suite.manifest["probes"]["acceptance"]["inspection_argv"]
    monkeypatch.setattr(suite, "receipts", Suite.receipts.__get__(suite))
    results = suite.execute()
    receipt = row(results, "receipts")
    assert (
        receipt["skipped"] and "probes.acceptance.inspection_argv" in receipt["detail"]
    )
    assert row(results, "probe/acceptance")["passed"]
    assert row(results, "probe/read")["passed"]
    assert (
        sum(method == "probe" and args[0] == "acceptance" for method, args in calls)
        == 1
    )


@pytest.mark.parametrize(
    "field,value", [("inspection_argv", []), ("inspection_effects", "bad")]
)
def test_synthesized_inspection_flags_depend_on_inspection_fields(plan, field, value):
    suite, calls = plan
    spec = suite.manifest["probes"]["acceptance"]
    spec["inspection_command"] = "tiny operation inspect"
    spec["inspection_argv"] = ["operation", "inspect", "--json"]
    suite.manifest["command_tree"].append(spec["inspection_command"])
    spec[field] = value
    results = suite.execute()
    inspection = row(results, "flag/" + spec["inspection_command"] + "/--json/before")
    assert (
        inspection["skipped"] and "probes.acceptance." + field in inspection["detail"]
    )
    assert row(results, "probe/acceptance")["passed"]


@pytest.mark.parametrize("raw", [None, [], 7])
def test_non_object_manifests_report_the_schema_problem(tmp_path, monkeypatch, raw):
    suite = Suite(raw, tmp_path, str(tmp_path))
    monkeypatch.setattr(
        suite, "run", lambda *a, **kw: pytest.fail("invalid root must not execute")
    )
    results = suite.execute()
    assert row(results, "manifest/$")["passed"] is False
    assert all(
        r.get("skipped") for r in results if not r["rule"].startswith("manifest/")
    )


@pytest.mark.parametrize("layout", ["prefix", "target"])
def test_schema_loads_from_installed_package_data(tmp_path, monkeypatch, layout):
    import shutil
    from pathlib import PurePosixPath
    from types import SimpleNamespace

    from goobits_cli.conformance import suite as module

    from .test_conformance import FIXTURES

    root = tmp_path / "install"
    package = root / "lib/python3.11/site-packages" if layout == "prefix" else root
    package.mkdir(parents=True, exist_ok=True)
    schema = root / "share/goobits-cli/docs/conformance-manifest.schema.json"
    schema.parent.mkdir(parents=True)
    shutil.copyfile(
        FIXTURES.parents[3] / "docs/conformance-manifest.schema.json", schema
    )
    record = PurePosixPath(
        "../../../share/goobits-cli/docs/conformance-manifest.schema.json"
    )
    monkeypatch.setattr(
        module, "__file__", str(package / "goobits_cli/conformance/suite.py")
    )
    monkeypatch.setattr(module, "files", lambda name: [record], raising=False)
    monkeypatch.setattr(
        module,
        "distribution",
        lambda name: SimpleNamespace(locate_file=lambda path: package / path),
        raising=False,
    )
    value = manifest()
    value["timeout_seconds"] = "bad"
    problems = Suite(value, tmp_path, str(tmp_path)).validate_manifest(collect=True)
    assert any(path == "timeout_seconds" for path, _ in problems)


def test_explicit_inspection_probe_does_not_depend_on_unused_inspection_metadata(plan):
    suite, calls = plan
    spec = suite.manifest["probes"]["completion"]
    spec["inspection_argv"] = []
    results = suite.execute()
    assert any(
        r["rule"] == "manifest/probes.completion.inspection_argv" for r in results
    )
    assert row(results, "probe/completion")["passed"]
    assert row(results, "flag/" + spec["command"] + "/--json/before")["passed"]


def test_valid_extra_help_case_is_independent_of_invalid_sibling(plan):
    suite, calls = plan
    cases = suite.manifest["help_version"]["cases"]
    extra = dict(cases[0], id=str(len(cases)))
    cases.extend([None, extra])
    results = suite.execute()
    assert any(r["rule"].startswith("manifest/help_version.cases.14") for r in results)
    assert row(results, "help-version/" + extra["id"])["passed"]
    assert any(method == "help_case" and args[0] is extra for method, args in calls)
