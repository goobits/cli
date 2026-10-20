# Goobits CLI Framework

Generate production-ready CLIs in Python, Node.js, TypeScript, or Rust from a single YAML configuration file.

All Goobits CLIs follow the [Goobits CLI standard](docs/cli-standard.md).

## Key Features

- **Multi-Language** - Python, Node.js, TypeScript, Rust from one config
- **Zero Boilerplate** - Define CLI structure in YAML, get working code
- **Minimal Output** - 3-4 files generated per language
- **Smart Merging** - Non-destructive package.json/Cargo.toml updates
- **Production Ready** - Setup scripts, validation
- **Self-Hosting** - Framework generates its own CLI

## Quick Start

```bash
# Install
pip install goobits-cli
# or
pipx install goobits-cli

# Create and build a project
mkdir my-cli && cd my-cli
goobits init
goobits build
./scripts/setup.sh install --dev
```

## Commands

| Command | Description |
|---------|-------------|
| `goobits build [config]` | Generate CLI from goobits.yaml |
| `goobits init [project_name]` | Create initial goobits.yaml |
| `goobits validate [config]` | Validate configuration without generating |
| `goobits migrate <path>` | Migrate YAML configs to 3.0.0 format |
| `goobits upgrade` | Upgrade goobits-cli to latest version |

### Command Options

**build**
- `-o`, `--output-dir` - Output directory for generated files
- `--output` - Output filename for generated CLI
- `--backup` - Create .bak files when overwriting

**init**
- `-t`, `--template` - Choose template (basic, advanced, api-client, text-processor)
- `--force` - Overwrite existing configuration

**validate**
- `-v`, `--verbose` - Show detailed validation information

**migrate**
- `--backup/--no-backup` - Create backup files (.bak), enabled by default
- `--dry-run` - Show changes without applying
- `--pattern` - File pattern for directory migration (default: "*.yaml")

**upgrade**
- `--source` - Upgrade source (pypi, git, local)
- `--version` - Specific version to install
- `--pre` - Include pre-release versions
- `--dry-run` - Show what would be upgraded without doing it

## Configuration

Create a `goobits.yaml` file:

```yaml
package_name: my-awesome-cli
command_name: mycli
display_name: "My Awesome CLI"
description: "A powerful CLI tool"
language: python

cli:
  name: mycli
  tagline: "Do awesome things"
  version: "1.0.0"
  commands:
    hello:
      desc: "Say hello"
      args:
        - name: name
          desc: "Name to greet"
          required: true
      options:
        - name: greeting
          short: g
          type: str
          desc: "Custom greeting"
          default: "Hello"
```

## Language Support

| Language | Files Generated | Configuration |
|----------|----------------|---------------|
| Python | `cli.py`, `app_hooks.py`, `setup.sh` | Default |
| Node.js | `cli.js`, `app_hooks.js`, `setup.sh` | `language: nodejs` |
| TypeScript | `cli.ts`, `app_hooks.ts`, `cli_types.d.ts`, `setup.sh` | `language: typescript` |
| Rust | `src/cli.rs`, `src/cli_hooks.rs`, `Cargo.toml`, `setup.sh` | `language: rust` |

### Language-Specific Options

**Python** (currently the only language with schema-validated options)
```yaml
language: python
python:
  minimum_version: "3.8"
  maximum_version: "3.13"
```

Other languages use sensible defaults (Node.js 14+, TypeScript ES2020, Rust edition 2021).

## Advanced Features

### Interactive Mode

Node.js and TypeScript generated CLIs support interactive mode:

```bash
mycli --interactive
```

### Hooks System

Implement business logic in language-specific hook files:

| Language | Hook File |
|----------|-----------|
| Python | `app_hooks.py` |
| Node.js | `app_hooks.js` |
| TypeScript | `app_hooks.ts` |
| Rust | `src/cli_hooks.rs` |

### Built-in Validation

- Disk space requirements
- System dependencies
- Runtime versions

## File Generation

### What Gets Generated

- CLI source file with all utilities embedded
- Hook file template for your business logic
- Setup script for installation
- Type definitions (TypeScript only)
- Cargo.toml (Rust only)

### What Does NOT Get Generated

- README.md (preserves your documentation)
- .gitignore (respects your version control)
- Auxiliary lib/ folders
- Separate config/error/util files

### Smart Manifest Handling

Existing `package.json`, `Cargo.toml`, or `pyproject.toml` files are preserved. Dependencies are merged without overwriting your configuration.

## Development

### From Source

```bash
git clone https://github.com/goobits/cli
cd goobits-cli
pip install -e .[dev,test]
```

### Testing

```bash
pytest src/tests/
pytest --cov=goobits_cli src/tests/
# Fast local run (skips heavy toolchain/network tests)
pytest src/tests/ -m "not heavy"
mypy src/goobits_cli/
```

## Documentation

- [CONTRIBUTING.md](CONTRIBUTING.md) - Contributing guidelines
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [CLAUDE.md](CLAUDE.md) - AI assistant instructions

## Examples

See `examples/` for sample configurations:

- `basic-demos/python-minimal.yaml` - Minimal Python CLI
- `basic-demos/rust-advanced.yaml` - Feature-rich Rust CLI
- `basic-demos/multi-language-demo.yaml` - Multi-language targets
- `advanced-features/nested-command-demo.yaml` - Nested subcommands

## License

Proprietary and confidential (`UNLICENSED`). Copyright (c) 2026 Goobits. All rights reserved. See [LICENSE](LICENSE).

## Links

- [GitHub Issues](https://github.com/goobits/cli/issues)
- [GitHub Discussions](https://github.com/goobits/cli/discussions)
