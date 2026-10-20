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

## Running the suite

Publish a version 1 JSON manifest and run:

```sh
goobits conformance check --manifest docs/conformance.example.json --json
```

The [usable JSON example](conformance.example.json) runs this repository's isolated
fixture CLI. Copy it and replace the executable, argv, documentation passages and
fixture hook for your tool. Validate authoring against the standalone
[JSON manifest schema](conformance-manifest.schema.json). For example, these are the
example's executable and fixture declarations (paths resolve from the manifest):

```json
{
  "executable": ["python3", "../src/tests/fixtures/conformance/conforming.py"],
  "fixture": {
    "argv": ["python3", "../src/tests/fixtures/conformance/conforming.py", "fixture"],
    "isolation": "GOOBITS_CONFORMANCE_STATE private directory"
  }
}
```

Exit 0 means all checks passed; exit 3 reports failed rules, section links and fix hints.
Only run trusted manifests: both argv arrays execute subprocesses. The suite supplies a
private `GOOBITS_CONFORMANCE_STATE`, HOME and TMPDIR in the system temporary directory
(or `MATILDA_ARTIFACT_ROOT` when set), strips inherited credentials, and
applies `fixture.env` to the target and hook. The hook receives one stdin JSON request
`{"action":"reset","scenario":"read"}` or `{"action":"inspect","scenario":"read"}`
and returns an observation object. Reset configures the isolated scenario; inspection
must observe actual backend/local state without mutating it.

Mechanically checked: envelope/error types, JSON/JSONL framing, canonical paths, exits,
shared flags on every declared path, stable verbose/quiet results, quiet diagnostic
patterns, all 14 required eager cases (including missing operands, root scope and
trailing JSON), offline help/version, noninteractive behavior, receipts and retry effects.
POSIX JSON TTY checks run with color-capable settings and no `NO_COLOR` override.
`help_required` maps documentation topics to concrete passages, not keywords: the suite
checks their presence, scope usage, schema identifiers/versions, exit numbers and retry
values. Authors still attest that those passages truthfully describe defaults, config
precedence, category selection, schemas, retry scope/retention and postconditions.
Completeness of the canonical tree, diagnostic classification and inapplicability
reasons is also declared; subprocess tests cannot discover undocumented interfaces.

`probes` declare safe argv, canonical command, optional exit/status, effects, expected
receipt paths and setup argv. Every scenario in the example must appear or have an
explicit `inapplicable` reason. `flag_probes` chooses a representative invocation per
path, including streams, failures and inspection commands. `volatile_paths` excludes
only documented generated identities/timestamps from result comparison; do not exclude
business results. `diagnostics.error` and `.deprecation` contain full-line regexes for
stderr allowed under quiet; informational diagnostics are never allowed there.
`help_version` declares native eager precedence, trailing JSON recognition and exact
named cases. The runner rejects omissions or shapes inconsistent with its case table.

Hook observations include `effects`, `prompts`, `service_calls`, forwarded `request_ids`
and a verified `postcondition`. Record actual injected payloads in `upstream_messages`
and derive `unknown_fields_sent`/`unknown_version_sent` from them. For retries expose the
stored `operation_id` and `request_id`; for expiry expose `clock`, `expired_entries`
(with `expires_at`) and derived `expired`. Mutation probes declare `equivalent_argv`
and `different_input` to check normalization, deduplication and conflicts. Accepted
receipts declare an exact inspection command and argv. Correlation forwarding is
checked when dispatch is observed or the probe declares `dispatch: true`.

Existing contracts may declare `envelope_mapping` (documented native field paths,
versions and status meanings) and `legacy_exits` (numeric exit strings to categories).
Help must include the deprecation and `canonical_exit_invocation`; mappings apply to
all checks, including interactions and retries. JSONL accepts any valid nonterminal
records allowed by the standard and requires a final terminal receipt.

Native [Rust](../src/tests/fixtures/conformance/pilots/rust.manifest.json) and
[TypeScript](../src/tests/fixtures/conformance/pilots/typescript.manifest.json) pilots
exercise distinct native eager parsers, mapped envelopes and legacy exits. The Python
test suite runs portable equivalents of both contracts without external toolchains.
To exercise the native sources, install Rust or TypeScript/Node separately. Build their
executables outside the checkout before running their manifests:

```sh
mkdir -p /var/tmp/matilda/workspace/conformance-pilots
rustc src/tests/fixtures/conformance/pilots/rust.rs -o /var/tmp/matilda/workspace/conformance-pilots/rust-pilot
tsc src/tests/fixtures/conformance/pilots/typescript.ts --target es2020 --outDir /var/tmp/matilda/workspace/conformance-pilots
goobits conformance check --manifest src/tests/fixtures/conformance/pilots/rust.manifest.json --json
goobits conformance check --manifest src/tests/fixtures/conformance/pilots/typescript.manifest.json --json
```
