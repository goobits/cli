# Goobits CLI standard

Goobits CLI owns this standard and conformance; each tool owns its commands,
payload schemas, and native parser. Generation and shared libraries are optional.
“MUST” requirements are conformance assertions, including on failure paths.

## Commands and flags

- Commands MUST use `tool noun verb`; command names and long flags MUST use
  kebab-case. Top-level `guide`, help, version, and established domain entrypoints
  are allowed exceptions. Tools MUST document their canonical command tree.
- Old executable, command, and flag spellings MUST remain deprecated aliases with
  identical behavior. Using any deprecated spelling MUST emit one warning on
  stderr per process, naming the replacements used; repeated uses MUST NOT emit
  more warnings. Aliases MUST report the canonical command in JSON.
- Every command MUST accept the shared flags before or after the command path:

| Flag | Required behavior |
| --- | --- |
| `--help` | Print usage, arguments, defaults, examples, side effects, and exit codes; exit 0 without services, credentials, or mutation. |
| `--version` | Print the CLI's own version; exit 0 offline without mutation. |
| `--json` | Select the machine contract below and disable prompts, color, and terminal controls. |
| `--quiet` | Suppress progress and informational diagnostics, retaining errors, deprecation warnings, and requested results. |
| `--verbose` | Add diagnostics on stderr without changing stdout's contract. |
| `--yes` | Answer confirmation questions affirmatively; never supply missing inputs or bypass authorization. |
| `--no-input` | Disable all prompts. |

`--quiet` and `--verbose` together MUST fail as usage (exit 2). Help/version
MUST honor `--json`: put help text or CLI version in `data` using the same envelope.
Tools MUST document configuration selection and precedence, including explicit
project/config options where supported.

## Interaction and output

A command MUST NOT prompt when stdin or stdout is not a TTY, or when `--json`
or `--no-input` is set. Missing required arguments MUST fail with exit 2;
required confirmation or an owner decision without `--yes` MUST fail with exit 4.
Neither case may perform the pending mutation.

With `--json`, stdout MUST contain exactly one UTF-8 JSON document followed by a
newline, including for parser, validation, and service failures. Diagnostics,
progress, and deprecation warnings MUST go to stderr. Human wording is not an API.
Explicitly documented streaming commands MUST instead emit JSONL: one complete
versioned envelope per line, no banners or multiline records, followed by one
terminal receipt when the stream ends normally or with a handled failure.
An abruptly killed process cannot promise a terminal document.

The default envelope extends vm's `presentation.rs`. All fields below are
required; nullable fields MUST be present as `null` when unavailable.

| Field | JSON type | Meaning |
| --- | --- | --- |
| `schema_version` | positive integer | Envelope contract version; initially `1`. |
| `command` | string | Canonical command path, e.g. `butter task list`; use the deepest resolved canonical path for parse failures. |
| `ok` | boolean | True exactly when `errors` is empty; acceptance alone does not mean work completed. |
| `data` | any JSON value or null | Tool-owned payload, partial result, or null when no result exists. |
| `errors` | array of error objects | Empty on success; nonempty on failure, including partial failure. |
| `request_id` | nonempty string | Correlation ID generated locally before dispatch, retained in downstream requests and receipts. |
| `status` | string enum | `accepted`, `completed`, or `failed`; streams may additionally use `running`. |

`accepted` and `running` MUST have `ok: true`; `completed` MUST have `ok: true`;
`failed` MUST have `ok: false`. Partial failures MUST use `failed`, retain useful
results in `data`, and exit nonzero. A locally generated request ID MUST remain
available even if a service cannot be reached.

Each error object MUST have exactly these required fields (additional documented
fields are allowed):

| Field | JSON type | Meaning |
| --- | --- | --- |
| `code` | nonempty string | Stable, tool-owned machine identifier; never derive it from human wording. |
| `message` | string | Human explanation; consumers MUST NOT branch on this text. |
| `retryable` | boolean | Whether retrying the same operation after a transient condition can succeed safely using its idempotency key. |
| `next_action` | nonempty string | Concrete recovery, inspection, or escalation instruction; state when no automatic retry is safe. |
| `target` | string or null | Affected resource identifier or input path, if known. |

A tool's existing envelope qualifies without wrapping or renaming fields if it
is versioned, carries stable error codes, and its published schema maps every
meaning above, including retryability, recovery, request identity, and work
status. Its help MUST identify that schema and mapping. An unversioned bare
payload does not qualify.

## Exit codes

Every command MUST document and use this table. For simultaneous failures, use
one exit category and preserve every error in `errors`; the documented command
contract MUST specify the category selection. Acceptance exits 0 only for commands
whose documented outcome is submission; waiting commands exit 0 only on completion.

| Code | Meaning |
| --- | --- |
| `0` | Successful completed operation, or acknowledged submission as documented. |
| `2` | Usage, missing input, invalid flag combination, or input validation failure. |
| `3` | Verification or conformance check failed after running. |
| `4` | Blocked, confirmation required, or owner action required, including denied authorization. |
| `5` | Runtime, service, transport, or internal error. |
| `124` | Deadline exceeded; work may still be running and MUST be inspected before retry. |
| `130` | Interrupted by SIGINT, when handled. |

## Work, retries, and versions

- Long work MUST distinguish submission from completion. An accepted receipt MUST
  contain `data.operation_id` (string) and `data.next_action` (string with an exact
  inspection command). Later receipts MUST retain the operation ID and request
  ID. A completed receipt MUST assert the command's documented postcondition;
  an acknowledgement alone MUST NOT claim completion.
- Mutations MUST accept `--idempotency-key KEY`. Retrying the same key, scope,
  and normalized input MUST return the same operation/result without duplicating
  effects, including after a lost response. Reusing a key with different input
  MUST fail with a stable conflict code and exit 2. Tools MUST publish the key's
  scope and retention period; after expiry callers MUST inspect before retrying.
  Generated keys MUST be returned as `data.idempotency_key` before work is
  acknowledged; callers needing recovery from a lost first response MUST supply
  their own key. A request ID identifies an invocation/operation trace; it MUST
  NOT silently substitute for a caller's retry key.
- CLI release versions and payload schema versions MUST be separate. `--version`
  reports the executable version; `schema_version` versions the envelope. Each
  payload MUST have a documented schema identifier/version, in its schema or
  payload, independently of both. Existing versioned envelopes keep their own
  version namespace. Breaking field types, meanings, or enum changes MUST use a
  new schema version. Readers MUST ignore unknown optional fields and reject
  unsupported versions with a stable error and recovery instruction. Producers
  MUST test supported consumer fixtures and deploy compatible readers before
  changing default writers.

## Butter pilot command tree

`butter` is the canonical executable; `butterboard` remains a deprecated alias.
Brackets mark optional inputs; `|` marks alternatives; `…` marks repetition.
Each leaf inherits the shared flags, output, retry, and exit rules above.

```text
butter task list [--mine] [filters]
butter task show TASK                         # status is a deprecated alias for show
butter task add
butter task claim|release|note|submit|comment|cancel TASK
butter task block|unblock TASK
butter task depend TASK --on TASK… [--clear]
butter task credit TASK
butter task label|priority|milestone TASK
butter task review TASK… --accept|--reject [--note TEXT]
butter image attach|get
butter agent hello
butter board hygiene
butter inbox list
butter guide
```

`task depend TASK --clear` MUST also work without `--on`; when both are supplied,
replace dependencies with the supplied set. Review MUST require exactly one of
`--accept` and `--reject`. Domain arguments, filters, and payloads remain owned by
Butter. For example, `butter task list --mine --json` returns command
`butter task list`, `status: "completed"`, `ok: true`, and `errors: []`.

## Decisions and evidence

- Use vm's envelope and exit categories, adding explicit receipt and retry fields,
  because the existing contract is the smallest shared base: `.llm/agents/cli-standard/inputs/presentation.rs`, `.llm/agents/cli-standard/inputs/agent-contract.rs`.
- Permit mapped existing envelopes instead of forcing one wrapper, because tools
  retain domain contracts: `.llm/agents/cli-standard/inputs/q4-cli-contracts-sol.md`, `.llm/agents/cli-standard/inputs/q4-cli-contracts-astra.md`.
- Keep native parsers and optional generation instead of mandatory codegen or a
  shared Rust crate, because the inventory spans Rust, Python, and TypeScript:
  `.llm/agents/cli-standard/inputs/cli-audit/inventory.md`, `.llm/agents/cli-standard/inputs/q4-cli-contracts-argon.md`, `.llm/agents/cli-standard/inputs/q4b-critique-oracle-argon.md`.
- Require local offline help and JSON noninteraction, because service availability
  must not prevent discovery: `.llm/agents/cli-standard/inputs/q4-cli-contracts-sol.md`, `.llm/agents/cli-standard/inputs/q4-cli-contracts-argon.md`.
- Require compatibility fixtures and reader-first rollout instead of assuming
  additive changes are safe, because consumers can reject new enum values:
  `.llm/agents/cli-standard/inputs/q4b-critique-oracle-sol.md`, `.llm/agents/cli-standard/inputs/q4b-critique-oracle-astra.md`.
