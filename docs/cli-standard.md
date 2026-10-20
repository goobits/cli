# Goobits CLI standard

Goobits CLI owns conformance; tools own commands, schemas, and native parsers.
Generation is optional. “MUST” requirements are subprocess assertions, including
failures.

## Commands and flags

- Commands MUST use `tool noun verb`; command names and long flags MUST use kebab-case.
  Top-level `guide`, help, version, and established domain entrypoints are allowed
  exceptions. Tools MUST document their canonical command tree.
- Old spellings MUST remain equivalent deprecated aliases, emitting exactly one stderr
  warning per process naming replacements. JSON MUST report canonical commands.
- Every command MUST accept shared flags before or after its path, except the
  help/version placement and precedence declared below:

| Flag | Required behavior |
| --- | --- |
| `--help` | Print usage, arguments, defaults, examples, side effects, and exit codes; exit 0 without services, credentials, or mutation. |
| `--version` | Print the CLI's own version; exit 0 offline without mutation. |
| `--json` | Select the machine contract below and disable prompts, color, and terminal controls. |
| `--quiet` | Suppress progress and informational diagnostics, retaining errors, deprecation warnings, and requested results. |
| `--verbose` | Add diagnostics on stderr without changing stdout's contract. |
| `--yes` | Answer confirmation questions affirmatively; never supply missing inputs or bypass authorization. |
| `--no-input` | Disable all prompts. |

Help/version target the parser scope where encountered: `tool --help noun verb`
describes the root; `tool noun verb --help` describes the leaf. Version identifies the
executable. The manifest MUST declare native eager precedence for combined help/version,
trailing-option handling, and exact JSON help/version invocations. Help/version MUST use
the JSON envelope with text/version in `data` when `--json` is recognized before
rendering. They MAY emit plain text only when the manifest declares eager rendering
before `--json` is parsed (or JSON is absent). Recognized help/version MUST exit 0 ahead
of missing operands and `--quiet --verbose` conflicts; otherwise that conflict MUST exit
2. Help MUST document configuration precedence and supported project/config options.

## Interaction and output

A command MUST NOT prompt when stdin or stdout is not a TTY, or when `--json` or
`--no-input` is set. Missing required arguments MUST fail with exit 2; required
confirmation or an owner decision without `--yes` MUST fail with exit 4. Neither case
may perform the pending mutation.

Except for the manifest-declared eager help/version case above, `--json` stdout MUST
contain exactly one UTF-8 JSON document followed by a newline, including parser,
validation, and service failures. Diagnostics, progress, and deprecation warnings MUST
go to stderr. Human wording is not an API. Explicitly documented streaming commands MUST
instead emit JSONL: one complete versioned envelope per line, no banners or multiline
records, followed by one terminal receipt when the stream ends normally or with a
handled failure. Unhandled crashes and abrupt termination cannot promise a terminal
document.

The envelope extends vm repository `rust/vm/src/presentation.rs` to reuse its base.
Fields MUST be present; unavailable nullable values MUST be `null`.

| Field | JSON type | Meaning |
| --- | --- | --- |
| `schema_version` | positive integer | Envelope contract version; initially `1`. |
| `command` | string | Canonical command path, e.g. `butter task list`; use the deepest resolved canonical path for parse failures. |
| `ok` | boolean | True exactly when `errors` is empty. |
| `data` | any JSON value or null | Tool-owned payload, partial result, or null when no result exists. |
| `errors` | array of error objects | Empty on success; nonempty on failure. |
| `request_id` | nonempty string | Correlation ID generated locally before dispatch, retained in downstream requests and receipts. |
| `status` | string enum | `accepted`, `completed`, or `failed`; streams may additionally use `running`. |

`accepted`, `running`, and `completed` MUST have `ok: true`; `failed` MUST have
`ok: false`. Partial failures MUST use `failed`, retain useful results in `data`,
and exit nonzero. A locally generated request ID MUST remain available even if a
service cannot be reached.

Each error object MUST have exactly these required fields (additional documented fields
are allowed):

| Field | JSON type | Meaning |
| --- | --- | --- |
| `code` | nonempty string | Tool-owned identifier, stable across message wording changes for the same failure. |
| `message` | string | Human explanation; not a machine discriminator. |
| `retryable` | boolean | Whether retrying the same operation after a transient condition can succeed safely using its idempotency key. |
| `next_action` | nonempty string | Recovery instruction, including when retry is unsafe. |
| `target` | string or null | Affected resource identifier or input path, if known. |

Existing versioned envelopes with stable error codes qualify through documented semantic
mappings, preserving domain contracts. Help MUST identify a schema and mapping covering
every meaning above.

## Exit codes

Help MUST document exit mappings and simultaneous-failure category selection; JSON MUST
preserve all errors. Submission commands may exit 0 on acceptance; waiting commands MUST
exit 0 only on completion. Categories derive from vm repository
`rust/vm/src/commands/agent/contract.rs`.

| Code | Meaning |
| --- | --- |
| `0` | Completed operation or documented acknowledged submission. |
| `1` | Reserved for unhandled crashes; conformance classifies as runtime failure like 5. |
| `2` | Usage, missing input, invalid flag combination, or input validation failure. |
| `3` | Verification or conformance check failed after running. |
| `4` | Blocked, confirmation required, or owner action required, including denied authorization. |
| `5` | Runtime, service, transport, or internal error. |
| `124` | Deadline exceeded; work may still be running; inspect before retry. |
| `130` | Interrupted by SIGINT, when handled. |

New commands MUST use canonical codes. Existing exit contracts MAY retain old codes
during documented deprecation; help and the manifest MUST map each legacy code to its
canonical category and identify the canonical-code invocation or version. Exit 1 always
denotes failure.

## Work, retries, and versions

- Long work MUST distinguish submission from completion. An accepted receipt MUST
  contain `data.operation_id` (string) and `data.next_action` (string with an exact
  inspection command). Later receipts MUST retain the operation ID and request ID. A
  completed receipt MUST assert the command's documented postcondition; an
  acknowledgement alone MUST NOT claim completion.
- Mutations MUST accept a caller-supplied retry key. New tools MUST name it
  `--idempotency-key`; existing tools MAY keep a documented spelling such as
  Butterboard's `--request-id`, including a documented dual correlation/retry role.
  Replaying the same key, scope, and normalized input MUST return the same
  operation/result without duplicating effects, including after a lost response. Reusing
  a key with different input MUST fail with a stable conflict code and exit 2. Tools
  MUST publish the key's scope and retention period; after expiry callers should inspect
  before retrying. Generated keys MUST appear in `data.idempotency_key` on
  acknowledgement; recovery from a lost first response requires caller-supplied keys.
  The manifest MUST identify the retry flag and receipt field; correlation-only IDs do
  not imply deduplication.
- CLI release versions and payload schema versions MUST be separate. `--version` reports
  the executable version; `schema_version` versions the envelope. Each payload MUST have
  a documented schema identifier/version, in its schema or payload, independently of
  both. Existing versioned envelopes keep their own version namespace. Readers MUST
  ignore unknown optional fields and reject unsupported versions with a stable error and
  recovery instruction.

## Conformance interface

Each tool MUST publish a versioned JSON conformance manifest at a documented repository
path. It MUST declare argv arrays for help/version precedence cases, JSON selection,
aliases, exits, safe read/mutation/stream/inspection commands, required inputs, schemas,
retry keys, and expected postconditions. For applicable service commands it MUST declare
a flag or environment variable selecting an isolated fake endpoint or local fixture
backend. The suite MUST be able to inject unavailability, denial, acceptance,
completion, timeout, lost responses after commit, unknown fields/versions, and retry-key
expiry, then inspect operation IDs, forwarded request IDs, and effect counts through
declared commands or fixture requests. Fixtures MUST need no production credentials or
production mutations. Tools without services MUST declare local state isolation and
equivalent probes for applicable mutation/retry behavior; inapplicable scenarios MUST be
explicit.

## Release practice

Breaking field types, meanings, or enum changes SHOULD use a new schema version.
Producers SHOULD test supported consumer fixtures and deploy compatible readers before
changing default writers; these process checks are outside subprocess conformance.

## Butter pilot example

`butterboard` remains a deprecated alias for `butter`. Representative commands:

```text
butter task list --mine
butter task show TASK
butter task review TASK --accept
butter guide
```

Butter owns its full command tree, arguments, and payloads.
