"""Regressions for declarations that were lost or executed after validation failed."""

import copy
import json
import re
from pathlib import Path

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


# Each schema property, array item and dynamic-map value has an independent case.
# Consumers describe externally visible check families, rather than runner internals.
def declaration_fields(schema, prefix=""):
    yield from ((prefix, schema),) if prefix else ()
    for key, child in schema.get("properties", {}).items():
        yield from declaration_fields(child, prefix + ("." if prefix else "") + key)
    if isinstance(schema.get("items"), dict):
        yield from declaration_fields(schema["items"], prefix + "[]")
    if isinstance(schema.get("additionalProperties"), dict):
        yield from declaration_fields(schema["additionalProperties"], prefix + ".*")


SCHEMA = json.loads(
    (Path(__file__).parents[3] / "docs/conformance-manifest.schema.json").read_text()
)
FIELD_CASES = [field for field, _ in declaration_fields(SCHEMA)]
# Semantic references need valid types as well as the structural matrix above.
MISSING = object()
REFERENCE_CASES = {
    "command_tree/invalid-dependency": ("command_tree.0", "tiny item bad_name"),
    "help_version/trailing-eager": ("help_version.trailing_options", None),
    "fixture/missing-argv": ("fixture.argv", MISSING),
    "probes/missing-read": ("probes.read", MISSING),
    "probes/missing-inspection-argv": ("probes.acceptance.inspection_argv", MISSING),
    "retry/missing-flag": ("retry.flag", MISSING),
    "flag_probes/outside": ("flag_probes.tiny item typo", "read"),
    "flag_probes/dangling": ("flag_probes.tiny item read", "missing-probe"),
    "flag_probes/outside-dangling": ("flag_probes.tiny item typo", "missing-probe"),
    "entrypoint_exceptions/outside": ("entrypoint_exceptions.0", "tiny typo"),
    "help_version.scope_usage/outside": (
        "help_version.scope_usage.tiny typo",
        "Usage: typo",
    ),
    "help_version.leaf_command/outside": ("help_version.leaf_command", "tiny typo"),
    "help_version.missing_command/outside": (
        "help_version.missing_command",
        "tiny typo",
    ),
    "help_version.cases/outside": ("help_version.cases.14.command", "tiny typo"),
    "aliases/outside": ("aliases.0.canonical", "tiny typo"),
    "probes/outside": ("probes.read.command", "tiny typo"),
    "probes.inspection/outside": ("probes.acceptance.inspection_command", "tiny typo"),
    "inapplicable/unknown": ("inapplicable.typo", "Unsupported"),
}


def field_context(value):
    """Supply optional declarations so each mutation starts from a valid manifest."""
    value.update(
        entrypoint_exceptions=["tiny item read"],
        timeout_seconds=10,
        inapplicable={"completion": "Not supported"},
        legacy_exits={"1": 2, "22": 2},
        canonical_exit_invocation="tiny --canonical-exits",
    )
    del value["probes"]["completion"]
    value["flag_probes"]["tiny item inspect"] = "expiry"
    value["command_tree"].append("tiny operation inspect")
    value["probes"]["acceptance"]["inspection_command"] = "tiny operation inspect"
    value["fixture"]["env"] = {"EXAMPLE": "value"}
    value["diagnostics"]["error"] = ["error: .*"]
    value["probes"]["read"].update(error_codes=["example"], setup_argv=["item", "read"])
    value["envelope_mapping"] = {
        "documentation": "Identity mapping documented in help",
        "fields": {
            k: k
            for k in "schema_version command ok data errors request_id status".split()
        },
        "error_fields": {
            k: k for k in "code message retryable next_action target".split()
        },
        "versions": ["1"],
        "statuses": {"accepted": "accepted"},
    }
    return value


def concrete_path(field):
    replacements = {
        "probes": "read",
        "flag_probes": "tiny item read",
        "inapplicable": "completion",
        "scope_usage": "tiny",
        "env": "EXAMPLE",
        "legacy_exits": "22",
        "statuses": "accepted",
    }
    parts = field.replace("[]", ".0").split(".")
    for i, part in enumerate(parts):
        if part == "*":
            parts[i] = replacements[parts[i - 1]]
    if parts[:2] == ["probes", "read"]:
        if any(p in parts for p in ("different_input", "equivalent_argv")):
            parts[1] = "mutation"
        elif any(
            p in parts
            for p in ("inspection_command", "inspection_argv", "inspection_effects")
        ):
            parts[1] = "acceptance"
    return parts


def set_declaration(value, parts, invalid):
    for part in parts[:-1]:
        if isinstance(value, list):
            value = value[int(part)]
        else:
            value = value.setdefault(part, {})
    if invalid is MISSING:
        del value[parts[-1]]
    elif isinstance(value, list):
        value[int(parts[-1])] = invalid
    else:
        value[parts[-1]] = invalid


def dependent_rules(field, parts, baseline):
    """Expected consumers, independent of the runner's dependency construction."""
    root = parts[0]
    rules = [
        r["rule"]
        for r in baseline
        if not r["rule"].startswith(("manifest", "legacy-exits"))
    ]
    if root in {"manifest_version", "executable", "fixture", "timeout_seconds"}:
        return rules
    patterns = []
    if root == "version":
        patterns = [
            "help-version/" + c["id"] + "$"
            for c in field_context(manifest())["help_version"]["cases"]
            if c["kind"] == "version"
        ]
    elif root in {"help_required", "payload_schema", "canonical_exit_invocation"}:
        patterns = [
            "help-version/(root-help.*|leaf-help|help-missing-input|text-conflict|json-help.*|help-version)$"
        ]
    elif root == "help_version":
        if len(parts) > 1 and parts[1] == "cases":
            case = (
                field_context(manifest())["help_version"]["cases"][int(parts[2])]
                if len(parts) > 2 and int(parts[2]) < 14
                else None
            )
            patterns = (
                ["help-version/" + re.escape(case["id"]) + "$"]
                if case
                else ["help-version/"]
            )
        elif len(parts) > 1 and parts[1] == "scope_usage":
            patterns = (
                ["help-version/(root-help.*|help-version)$"]
                if len(parts) > 2
                else [
                    "help-version/(root-help.*|leaf-help|help-missing-input|text-conflict|json-help.*|help-version)$"
                ]
            )
        elif len(parts) > 1 and parts[1] in {"precedence", "trailing_options"}:
            patterns = (
                ["help-version/(help-version|version-help)$"]
                if parts[1] == "precedence"
                else ["help-version/json-.*-after$"]
            )
        elif len(parts) > 1 and parts[1].startswith("leaf_"):
            patterns = [
                "help-version/(leaf-help|text-conflict|version-conflict|json-.*)$"
            ] + (["help-version/root-help-command$"] if parts[1] == "leaf_argv" else [])
        elif len(parts) > 1 and parts[1].startswith("missing_"):
            patterns = ["help-version/(help|version)-missing-input$"]
        else:
            patterns = ["help-version/"]
    elif root == "name":
        patterns = ["help-version/(root-.*|help-version|version-help)$"]
    elif root in {"legacy_exits", "envelope_mapping"}:
        patterns = [r"(?!help-version/)"]
        patterns += (
            [
                "help-version/(root-help.*|leaf-help|help-missing-input|text-conflict|json-help.*|help-version)$"
            ]
            if root == "legacy_exits"
            else ["help-version/json-"]
        )
    elif root in {"volatile_paths", "diagnostics"}:
        patterns = ["flag/.*/--quiet/"] + (
            ["flag/.*/--verbose/"] if root == "volatile_paths" else []
        )
    elif root == "aliases":
        patterns = ["alias/"]
    elif root == "retry":
        patterns = ["retry/"]
    elif root == "probes":
        if len(parts) == 1:
            patterns = [r"(?!help-version/)"]
        else:
            name = parts[1]
            if len(parts) > 2 and parts[2] in {"different_input", "equivalent_argv"}:
                patterns = ["retry/" + name + "$"]
            elif len(parts) > 2 and parts[2] in {
                "inspection_argv",
                "inspection_effects",
            }:
                patterns = [
                    "(?:flag|json/color-capable-tty)/tiny operation inspect(?:/|$)"
                ] + (["receipts$"] if parts[2] == "inspection_argv" else [])
            else:
                patterns = [
                    "(?:probe|retry|stable-error|interaction)/"
                    + re.escape(name)
                    + "(?:/|$)"
                ]
                command = field_context(manifest())["probes"][name]["command"]
                patterns += [
                    "(?:flag|json/color-capable-tty)/" + re.escape(command) + "(?:/|$)"
                ]
                if name == "acceptance":
                    patterns += [
                        "receipts$",
                        "(?:flag|json/color-capable-tty)/tiny operation inspect(?:/|$)",
                    ]
                if name == "mutation":
                    patterns += ["generated-retry-key$"]
                if name == "read":
                    patterns += ["alias/"]
    elif root in {"command_tree", "flag_probes"}:
        patterns = (
            ["flag/", "json/color-capable-tty/"]
            if len(parts) == 1
            else [
                "(?:flag|json/color-capable-tty)/"
                + re.escape(parts[1] if root == "flag_probes" else "tiny item read")
                + "(?:/|$)"
            ]
        )
    elif root not in {"$schema", "entrypoint_exceptions", "long_flags", "inapplicable"}:
        raise AssertionError("Declare consumers for schema field " + field)
    return [rule for rule in rules if any(re.match(p, rule) for p in patterns)]


@pytest.mark.parametrize("field", FIELD_CASES + list(REFERENCE_CASES))
def test_every_schema_declaration_reports_unusable_values_and_skips_consumers(
    plan, field, monkeypatch
):
    suite, calls = plan
    suite.manifest = field_context(suite.manifest)
    suite.raw_manifest = suite.manifest
    if field == "help_version/trailing-eager":
        suite.manifest["help_version"]["trailing_options"] = "eager"
        for case in suite.manifest["help_version"]["cases"]:
            if case["id"] in {"json-help-after", "json-version-after"}:
                case["json"] = False
    baseline = suite.execute()
    assert not any(r["passed"] is False for r in baseline), baseline
    suite.results, calls[:] = [], []
    active, invoked = [None], set()
    original_check = suite.check

    def track(rule, *args):
        active[0] = rule
        return original_check(rule, *args)

    monkeypatch.setattr(suite, "check", track)
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
        monkeypatch.setattr(suite, method, lambda *args: invoked.add(active[0]))
    if field in REFERENCE_CASES:
        path, invalid = REFERENCE_CASES[field]
        parts = path.split(".")
        if field == "help_version.cases/outside":
            suite.manifest["help_version"]["cases"].append(
                dict(suite.manifest["help_version"]["cases"][0], id="extra")
            )
        if field.startswith("flag_probes/outside"):
            expected = [
                r["rule"].replace("tiny item read", "tiny item typo")
                for r in baseline
                if r["rule"].startswith(
                    ("flag/tiny item read/", "json/color-capable-tty/tiny item read")
                )
            ]
        elif field == "help_version.cases/outside":
            expected = ["help-version/extra"]
        elif field == "help_version.scope_usage/outside":
            expected = []
        else:
            expected = dependent_rules(field, parts, baseline)
    else:
        parts, invalid = concrete_path(field), None
        expected = dependent_rules(field, parts, baseline)
    set_declaration(suite.manifest, parts, invalid)
    if field == "command_tree/invalid-dependency":
        suite.manifest["probes"]["read"]["command"] = invalid
        suite.manifest["flag_probes"][invalid] = suite.manifest["flag_probes"].pop(
            "tiny item read"
        )
        names = {
            n
            for n, p in suite.manifest["probes"].items()
            if p["command"] in {"tiny item read", invalid}
        }
        expected = [
            r["rule"].replace("tiny item read", invalid)
            for r in baseline
            if r["rule"].startswith(
                ("flag/tiny item read/", "json/color-capable-tty/tiny item read")
            )
        ]
        expected += [
            r["rule"]
            for r in baseline
            if r["rule"].startswith("alias/")
            or any(
                r["rule"] == family + "/" + n
                or r["rule"].startswith(family + "/" + n + "/")
                for n in names
                for family in ("probe", "stable-error", "interaction")
            )
        ]
    results = suite.execute()
    path = ".".join(parts)
    assert any(
        (
            r["rule"].startswith("manifest/" + path)
            or (
                path.startswith(r["rule"][len("manifest/") :] + ".")
                and r["rule"].startswith("manifest/")
            )
        )
        and r["passed"] is False
        for r in results
    ), path
    for rule in expected:
        result = row(results, rule)
        assert result.get("skipped") and result["detail"].startswith("Depends on: "), (
            field,
            result,
        )
        assert rule not in invoked, rule
    # Explicitly inapplicable scenarios have no executable case, but a broken reason
    # must retain that scenario as a skip instead of silently dropping it.
    if parts[:2] == ["inapplicable", "completion"]:
        assert row(results, "probe/completion").get("skipped")


def test_inspection_receipt_may_include_required_operands(plan):
    suite, _ = plan
    suite.manifest["probes"]["acceptance"]["inspection_command"] += " OPERATION"
    assert not suite.validate_manifest(collect=True)


def test_schema_matrix_has_no_missing_properties():
    assert len(FIELD_CASES) == len(set(FIELD_CASES))
    assert set(SCHEMA["properties"]) <= set(FIELD_CASES)
