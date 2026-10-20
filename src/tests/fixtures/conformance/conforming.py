"""An isolated CLI and persistent fake service with observable fault injection."""

import json
import os
import sys
import uuid
from pathlib import Path

STATE = Path(os.environ["GOOBITS_CONFORMANCE_STATE"]) / "state.json"
VERSION = "1.2.3"
DOCS = {
    "usage": "Usage: tiny item read|require|write|submit|inspect|stream|fail [OPTIONS]",
    "arguments": "Arguments: require INPUT is mandatory; write --value TEXT selects content.",
    "defaults": "Defaults: --value=value; --scope=item; no configuration files.",
    "examples": "Examples: tiny item read --json; tiny item require INPUT --json.",
    "side effects": "Side effects: write stores content; submit creates work; inspect completes pending work.",
    "exit codes": "Exit codes: 0 completed/accepted, 1 crash, 2 usage, 3 verification, 4 blocked, 5 service, 124 deadline, 130 interrupted.",
    "configuration precedence": "Configuration precedence: explicit flags > defaults; config/project files are unsupported.",
    "project": "Project options: none supported.",
    "config": "Config options: none supported.",
    "schema": "Payload schema: tiny.payload version 1, independent of executable 1.2.3.",
    "mapping": "Mapping: identity Goobits envelope and error fields; docs/cli-standard.md#interaction-and-output.",
    "simultaneous failures": "Simultaneous failures: retain all errors; service errors select category 5 before validation category 2.",
    "scope": "Retry scope: resource selected by --scope, default item; same scope and key identify one operation.",
    "retention": "Retry retention: 24h; inspect tiny item inspect before retrying an expired key.",
}
HELP = "\n".join(DOCS.values())


class Failure(Exception):
    def __init__(self, code, errors, data=None):
        self.code, self.errors, self.data = code, errors, data


def error(code, message=None, retryable=False):
    return {
        "code": code,
        "message": message or code,
        "retryable": retryable,
        "next_action": "Inspect tiny item inspect before retrying",
        "target": None,
    }


def save(state):
    STATE.write_text(json.dumps(state), encoding="utf-8")


def observe(state):
    expired = [
        entry
        for entry in state["ledger"].values()
        if entry["expires_at"] < state["clock"]
    ]
    operations = list(state["operations"].values())
    last = operations[-1] if operations else None
    # These facts are derived from the persisted service records, not success flags.
    completed = bool(
        last
        and last["status"] == "completed"
        and state["resources"].get(last["scope"]) == last["input"]
    )
    reads = state["upstream_messages"]
    read_ok = bool(
        reads
        and reads[-1].get("value") == state["resources"].get("item")
        and reads[-1]["schema_version"] == 1
    )
    return dict(
        state,
        effects=len(state["effects_log"]),
        service_calls=len(state["requests"]),
        request_ids=[r["request_id"] for r in state["requests"]],
        operation_id=last["operation_id"] if last else None,
        request_id=last["request_id"] if last else None,
        postcondition=completed if operations else read_ok,
        expired=bool(expired),
        expired_entries=expired,
        unknown_fields_sent=any("future_optional" in m for m in reads),
        unknown_version_sent=any(m["schema_version"] != 1 for m in reads),
    )


def backend(
    state, action, request_id, key=None, value="value", scope="item", defect=""
):
    state["requests"].append(
        {
            "request_id": request_id,
            "action": action,
            "key": key,
            "scope": scope,
            "input": value,
        }
    )
    scenario = state["scenario"]
    try:
        if scenario == "unavailable":
            raise ConnectionError("fake endpoint unavailable")
        if scenario == "timeout":
            raise TimeoutError("fake deadline exceeded")
        if scenario == "interrupt":
            raise KeyboardInterrupt()
        if scenario in {"denial", "stream-failure"}:
            raise Failure(4 if scenario == "denial" else 5, [error(scenario)])
        if action in {"write", "submit"}:
            normalized = value.strip()
            cache_key = scope + ":" + key
            entry = state["ledger"].get(cache_key)
            if entry and entry["expires_at"] >= state["clock"] and defect != "dedup":
                if entry["input"] != normalized and defect != "conflict":
                    raise Failure(2, [error("conflict")])
                return json.dumps(state["operations"][entry["operation_id"]])
            operation = {
                "operation_id": str(uuid.uuid4()),
                "request_id": request_id,
                "scope": scope,
                "input": normalized,
                "idempotency_key": key,
                "status": "accepted" if action == "submit" else "completed",
            }
            state["operations"][operation["operation_id"]] = operation
            state["ledger"][cache_key] = dict(
                operation, expires_at=state["clock"] + 86400
            )
            if action == "write":
                state["resources"][scope] = normalized
                state["effects_log"].append(
                    {"operation_id": operation["operation_id"], "value": normalized}
                )
            if scenario == "lost-response" and not state["lost"]:
                state["lost"] = True
                raise Failure(5, [error("lost_response", retryable=True)], operation)
            return json.dumps(operation)
        if action == "inspect" and state["operations"]:
            operation = list(state["operations"].values())[-1]
            if operation["status"] == "accepted" and defect != "completion":
                state["resources"][operation["scope"]] = operation["input"]
                state["effects_log"].append(
                    {
                        "operation_id": operation["operation_id"],
                        "value": operation["input"],
                    }
                )
                operation["status"] = "completed"
            return json.dumps(
                dict(operation, status="completed", next_action="tiny item inspect")
            )
        message = {
            "schema_version": 999 if scenario == "unknown-version" else 1,
            "value": state["resources"]["item"],
        }
        if scenario == "unknown-fields":
            message["future_optional"] = {"ignored": True}
        state["upstream_messages"].append(message)
        return json.dumps(message)
    finally:
        save(state)


def fixture(request):
    if request["action"] == "reset":
        state = {
            "scenario": request["scenario"],
            "clock": 0,
            "prompts": 0,
            "requests": [],
            "upstream_messages": [],
            "ledger": {},
            "operations": {},
            "effects_log": [],
            "resources": {"item": "value"},
            "lost": False,
        }
        save(state)
        if request["scenario"] == "expiry":
            backend(state, "write", str(uuid.uuid4()), "expired-key")
            if os.environ.get("GOOBITS_BREAK") != "expiry":
                state["clock"] = 86401
            save(state)
    else:
        state = json.loads(STATE.read_text())
    return observe(state)


def main(broken=False):
    args = sys.argv[1:]
    defect = os.environ.get("GOOBITS_BREAK", "") if broken else ""
    if args == ["fixture"]:
        print(json.dumps(fixture(json.load(sys.stdin))))
        return
    state = json.loads(STATE.read_text())
    scenario = state["scenario"]
    request_id = str(uuid.uuid4())  # allocated before parsing or any service dispatch
    command, code, status, data, errors = "tiny", 0, "completed", None, []
    eager = next((a for a in args if a in {"--help", "--version"}), None)
    words = [a for a in args if not a.startswith("--")]
    if "item" in args:
        prefix = args[: args.index(eager)] if eager else args
        if "item" in prefix:
            command = "tiny item"
            if len(words) >= 2:
                command += " " + ("read" if words[1] == "old-read" else words[1])
    try:
        if eager:
            if (
                defect == "help-missing"
                and "require" in args
                and not any(a == "INPUT" for a in args)
            ):
                raise Failure(2, [error("missing-input")])
            if eager == "--help":
                scope = "tiny item require" if defect == "root-scope" else command
                usage = (
                    "Usage: "
                    + scope
                    + (" INPUT" if scope.endswith("require") else "")
                    + " [OPTIONS]"
                )
                passages = [v for k, v in DOCS.items() if defect != "help-doc/" + k]
                text = usage + "\n" + "\n".join(passages)
                data = {"text": " ".join(DOCS) if defect == "help-keywords" else text}
            else:
                data = {"version": VERSION}
            if defect == "help":
                code = 5
        else:
            if "old-read" in args or defect == "quiet-warning":
                print(
                    "deprecated: old option; use --value"
                    if defect == "quiet-warning"
                    else "deprecated: use tiny item read",
                    file=sys.stderr,
                )
                if defect == "alias":
                    print("deprecated: use tiny item read", file=sys.stderr)
            if "--verbose" in args and defect != "verbose":
                print("diagnostic", file=sys.stderr)
            allowed = {
                "--json",
                "--quiet",
                "--verbose",
                "--yes",
                "--no-input",
                "--changed",
                "--confirm",
                "--owner",
                "--verify",
                "--value",
                "--scope",
                "--idempotency-key",
            }
            if any(a.startswith("--") and a not in allowed for a in args):
                raise Failure(2, [error("invalid-flag")])
            if "--quiet" in args and "--verbose" in args:
                raise Failure(2, [error("conflict")])

            def option(flag, default):
                return args[args.index(flag) + 1] if flag in args else default

            value, scope = option("--value", "value"), option("--scope", "item")
            if "require" in args and "INPUT" not in args:
                raise Failure(2, [error("missing-input")])
            if not value.strip():
                raise Failure(2, [error("invalid-input")])
            if "--owner" in args or ("--confirm" in args and "--yes" not in args):
                raise Failure(
                    4,
                    [error("owner-decision" if "--owner" in args else "confirmation")],
                )
            verb = command.split()[-1]
            action = verb if verb in {"write", "submit", "inspect"} else "read"
            key = option("--idempotency-key", str(uuid.uuid4()))
            if "--changed" in args:
                value = "changed"
            reply = json.loads(
                backend(state, action, request_id, key, value, scope, defect)
            )
            if "schema_version" in reply:
                if reply["schema_version"] != 1 and defect != "reader-version":
                    raise Failure(
                        2,
                        [
                            error(
                                "unknown-version",
                                "Unsupported upstream payload version; upgrade the reader",
                            )
                        ],
                    )
                if "future_optional" in reply and defect == "reader-fields":
                    raise Failure(2, [error("unknown-fields")])
                data = {"schema": "tiny.payload/1", "value": reply["value"]}
            else:
                request_id, status = reply["request_id"], reply["status"]
                data = {
                    "schema": "tiny.payload/1",
                    "operation_id": reply["operation_id"],
                    "idempotency_key": reply["idempotency_key"],
                    "next_action": "tiny item inspect",
                }
            if scenario == "expiry":
                data["next_action"] = "tiny item inspect"
            if "--verify" in args and data.get("value") != "expected":
                raise Failure(3, [error("verification")], data)
            if scenario in {"partial-failure", "multiple-errors"}:
                raise Failure(
                    5,
                    [error("partial-failure")]
                    * (2 if scenario == "multiple-errors" else 1),
                    data,
                )
    except ConnectionError as exc:
        code, errors = 5, [error("unavailable", str(exc))]
    except TimeoutError as exc:
        code, errors = 124, [error("timeout", str(exc))]
    except KeyboardInterrupt:
        code, errors = 130, [error("interrupt")]
    except Failure as exc:
        code, errors, data = exc.code, exc.errors, exc.data
    if errors:
        status = "failed"
    doc = {
        "schema_version": 1,
        "command": command,
        "ok": not errors,
        "data": data,
        "errors": errors,
        "request_id": request_id,
        "status": status,
    }
    if defect == "quiet-error":
        for item in errors:
            print(item["message"], file=sys.stderr)
    if defect == "request":
        doc["request_id"] = "not-forwarded"
    if defect == "exit":
        code = 2
    if defect == "canonical":
        doc["command"] = "tiny old-read"
    if defect == "envelope":
        doc["request_id"] = ""
    if defect == "stdout":
        print("diagnostic on stdout")
    if defect == "quiet" and "--quiet" in args:
        print("informational", file=sys.stderr)
    if defect == "prompt":
        state["prompts"] += 1
    if defect == "effects":
        state["effects_log"].append({"unexpected": True})
    if defect == "acceptance" and data:
        data.pop("operation_id", None)
    if defect == "receipt" and "inspect" in args and data:
        data["operation_id"] = "different-operation"
    if defect == "verbose-result" and "--verbose" in args and data:
        data["value"] = "changed by verbose"
    if defect == "unknown":
        state["upstream_messages"] = []
    if broken and not defect:
        print("prompt? banner and diagnostics on stdout")
        doc.update(
            schema_version=True,
            command="tiny old-read",
            ok=True,
            status="accepted",
            request_id="",
        )
        doc["errors"] = [
            {
                "code": "",
                "message": 1,
                "retryable": "yes",
                "next_action": "",
                "target": 1,
            }
        ]
        state["prompts"] += 1
        state["effects_log"].append({"unexpected": True})
        code = 1
    save(state)
    if defect == "legacy-exits":
        code = {2: 22, 4: 44}.get(code, code)
    if eager and (
        "--json" not in args
        or (defect == "json-eager" and args.index("--json") > args.index(eager))
    ):
        print(data["text"] if eager == "--help" else VERSION)
    else:
        if (
            "--json" in args
            and sys.stdout.isatty()
            and (
                defect == "json-color"
                or (
                    defect == "json-eager"
                    and eager
                    and args.index("--json") > args.index(eager)
                )
            )
        ):
            print("\x1b[31m", end="")
        if "stream" in args and not eager:
            print(json.dumps(dict(doc, status="accepted", ok=True, errors=[])))
        print(json.dumps(doc))
    sys.exit(code)


if __name__ == "__main__":
    main()
