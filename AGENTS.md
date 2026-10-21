# AGENTS.md

Local guidance for Goobits CLI. The monorepo-level `/workspace/AGENTS.md` instructions also apply.

## Project

- Package and command: `goobits-cli` / `goobits`
- Python: 3.8-3.13
- Purpose: generate Python, Node.js, TypeScript, and Rust CLIs from `goobits.yaml`

## Commands

```bash
python -m pip install -e '.[dev,test]'
goobits validate goobits.yaml
goobits build goobits.yaml
make test-fast SKIP_INSTALL_DEV=1
make lint
make typecheck
```

Use the project virtual environment, not an unrelated global `goobits` installation. Full cross-language checks may require Node.js and Cargo.

## Architecture

- `main.py`: Typer entry point and command registration
- `commands/`: build, init, validate, migrate, and upgrade handlers
- `core/schemas.py`: `goobits.yaml` validation models
- `universal/ir/`: language-independent configuration model
- `universal/engine/`: generation pipeline and stages
- `universal/renderers/`: language-specific output mapping
- `universal/components/`: Jinja templates for generated artifacts
- `universal/formatters/`: language-specific help and source formatting
- `validation/`: generated-project validation
- `src/tests/`: unit, integration, acceptance, parity, and end-to-end coverage

The generation path is:

```text
goobits.yaml -> schema -> IR -> renderer/templates -> generated project files
```

Do not add a language-specific path that bypasses the shared schema and IR unless the format truly cannot use them.

## Generated and preserved files

- `src/goobits_cli/generated_cli.py` and `scripts/setup.sh` are self-hosting outputs. Change `goobits.yaml`, templates, or generation code and regenerate them; do not hand-edit them.
- Generated hook files are user-owned extension points. The builder must preserve an existing hook implementation.
- Keep generated fixtures in tests only when they assert a behavior that cannot be checked from generated content in memory.

## Change discipline

- Read the schema, IR builder, renderer, component template, and focused tests before changing generated behavior.
- Test every affected target language; shared template changes can alter all four outputs.
- Keep artifact, coverage, toolchain, and package caches under `MATILDA_ARTIFACT_ROOT`, never in `/workspace`.
- Avoid hard-coded performance or completeness claims in documentation; tests and release notes own measured results.
- Never commit unless explicitly requested.
- Shared macOS/Linux checkouts should use `core.filemode=false`; record executable bits with `git update-index --chmod=+x PATH` when needed.

<!-- butterboard-task-authority:start -->

## Current work lives in Butterboard

Tasks for `goobits-cli` live in Butterboard. Before working on them, run `butter guide`
in this repository and follow it. Miko authorizes you to manage this project's tasks with its key.

Host (Mac): `butter` is in `~/.local/bin`; if missing, run `~/projects/butterboard/scripts/install-cli.sh`.
VM guest: `butter` is in `~/.local/bin`; if missing, run `vm tools update butterboard`.

Board: https://butterboard.butter/cli

Deploys: only `live-prod` and `live-dev` deploy hosted sites; ops promotes after Miko approves. Never create or commit to them locally.
Private Butterbox services (Butterboard, Butterland and other `*.butter` apps on loopback) deploy locally with their own scripts.
See `~/projects/AGENTS.md` › Deploys; for hosted promotion, hand off the repo, target, exact commit SHA and what changed.

<!-- butterboard-task-authority:end -->
