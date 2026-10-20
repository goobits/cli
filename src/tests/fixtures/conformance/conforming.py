"""Tiny isolated target and fixture protocol, used only through subprocesses."""

import json
import os
import sys
from pathlib import Path

STATE = Path(os.environ["GOOBITS_CONFORMANCE_STATE"]) / "state.json"
BASE = {
    "effects": 0,
    "prompts": 0,
    "service_calls": 0,
    "request_ids": [],
    "postcondition": True,
    "operation_id": "operation-1",
    "request_id": "request-1",
}
HELP = (
    "Usage arguments defaults examples side effects exit codes configuration precedence "
    "project config schema mapping simultaneous failures retry scope retention payload/1"
)


def main(broken=False):
    args = sys.argv[1:]
    defect = os.environ.get("GOOBITS_BREAK", "") if broken else ""
    if args == ["fixture"]:
        request = json.load(sys.stdin)
        if request["action"] == "reset":
            state = dict(BASE, scenario=request["scenario"], attempts=0)
            STATE.write_text(json.dumps(state))
        else:
            state = json.loads(STATE.read_text())
        print(json.dumps(state))
        return
    state = json.loads(STATE.read_text())
    scenario = state["scenario"]
    command = "tiny item read"
    code = 0
    status = "completed"
    data = {"schema": "tiny.payload/1", "value": "value"}
    errors = []
    eager = next((a for a in args if a in ("--help", "--version")), None)
    if eager:
        data = {"text": HELP} if eager == "--help" else {"version": "1.2.3"}
        command = (
            "tiny"
            if args.index(eager) == 0
            or (args[0] == "--json" and args.index(eager) == 1)
            else command
        )
    else:
        if "old-read" in args:
            if defect == "alias":
                print("deprecated: use tiny item read", file=sys.stderr)
            print("deprecated: use tiny item read", file=sys.stderr)
        if "--verbose" in args and defect != "verbose":
            print("diagnostic", file=sys.stderr)
        codes = {
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
            "partial-failure": 5,
            "multiple-errors": 5,
            "unknown-version": 2,
            "stream-failure": 5,
        }
        code = codes.get(scenario, 0)
        if scenario == "confirmation-yes":
            state["effects"] = 1
        if scenario in ("mutation", "lost-response"):
            command = "tiny item write"
            state["attempts"] += 1
            if "--changed" in args:
                code = 2
            else:
                state["effects"] = 1
            key = (
                args[args.index("--idempotency-key") + 1]
                if "--idempotency-key" in args
                else "generated-key"
            )
            data = {
                "schema": "tiny.payload/1",
                "operation_id": state["operation_id"],
                "idempotency_key": key,
            }
        elif scenario in ("acceptance", "completion"):
            status = (
                "completed"
                if "inspect" in args or scenario == "completion"
                else "accepted"
            )
            command = "tiny item inspect" if "inspect" in args else "tiny item submit"
            data = {
                "schema": "tiny.payload/1",
                "operation_id": state["operation_id"],
                "next_action": "tiny item inspect",
            }
        if code:
            status = "failed"
            error = {
                "code": "conflict" if "--changed" in args else scenario,
                "message": "failure",
                "retryable": False,
                "next_action": "inspect before retry",
                "target": None,
            }
            errors = [error] * (2 if scenario == "multiple-errors" else 1)
        if defect != "request":
            state["request_ids"].append(state["request_id"])
    STATE.write_text(json.dumps(state))
    doc = {
        "schema_version": 1,
        "command": command,
        "ok": not errors,
        "data": data,
        "errors": errors,
        "request_id": state["request_id"],
        "status": status,
    }
    if scenario == "expiry":
        state["expired"] = True
        doc["data"]["next_action"] = "tiny item inspect"
    if scenario == "unknown-fields":
        state["unknown_fields_sent"] = True
    if scenario == "unknown-version":
        state["unknown_version_sent"] = True
    STATE.write_text(json.dumps(state))
    if defect:
        if defect == "help":
            code = 5
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
            state["prompts"] = 1
        if defect == "effects":
            state["effects"] += 1
        if defect == "acceptance":
            doc["data"].pop("operation_id", None)
        if defect == "completion":
            state["postcondition"] = False
        if defect == "dedup":
            state["effects"] = state["attempts"]
        if defect == "conflict" and "--changed" in args:
            code = 0
            doc.update(ok=True, errors=[], status="completed")
        if defect == "receipt" and "inspect" in args:
            doc["data"]["operation_id"] = "different-operation"
        if defect == "expiry":
            state["expired"] = False
        if defect == "unknown":
            state["unknown_fields_sent"] = False
            state["unknown_version_sent"] = False
        STATE.write_text(json.dumps(state))
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
        state.update(
            prompts=1,
            effects=state["effects"] + 1,
            service_calls=1,
            postcondition=False,
        )
        STATE.write_text(json.dumps(state))
        code = 1
    if scenario == "lost-response" and state["attempts"] == 1 and not eager:
        doc.update(
            ok=False,
            status="failed",
            errors=[
                {
                    "code": "lost_response",
                    "message": "Response lost after commit",
                    "retryable": True,
                    "next_action": "Retry with the same key",
                    "target": None,
                }
            ],
        )
        print(json.dumps(doc))
        sys.exit(5)
    if eager and "--json" not in args:
        print(HELP if eager == "--help" else "1.2.3")
    else:
        if scenario.startswith("stream") and not eager:
            print(json.dumps(dict(doc, status="running", ok=True, errors=[])))
        print(json.dumps(doc))
    sys.exit(code)


if __name__ == "__main__":
    main()
