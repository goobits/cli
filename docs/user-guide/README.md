# User Guide

Complete documentation for using the Goobits CLI Framework.

## Quick Navigation

- **[Configuration Reference](configuration.md)** - Complete `goobits.yaml` schema and examples
- **[Troubleshooting Guide](troubleshooting.md)** - Common issues and solutions

## Getting Started

1. **Installation**
   ```bash
   pipx install goobits-cli
   ```

2. **Create a new project**
   ```bash
   mkdir my-awesome-cli && cd my-awesome-cli
   goobits init
   ```

3. **Build your CLI**
   ```bash
   goobits build
   ./setup.sh install --dev
   ```

## Key Concepts

### Configuration File
The `goobits.yaml` file defines your CLI structure, commands, and behavior. See [Configuration Reference](configuration.md) for complete details.

### Hook Files
Business logic is implemented in language-specific hook files:
- **Python**: `cli_hooks.py`
- **Node.js**: `cli_hooks.mjs`
- **TypeScript**: `cli_hooks.ts`
- **Rust**: `src/cli_hooks.rs`

### Generated Files
The framework generates:
- CLI implementation (language-specific)
- Setup script (`setup.sh`)
- Package configuration files
- Shell completion scripts

## Language Support

| Language   | Status | Framework | Performance |
|------------|--------|-----------|-------------|
| Python     | ✅ Production | rich-click | ~72ms startup |
| Node.js    | ✅ Production | Commander.js | ~24ms startup |
| TypeScript | ✅ Production | Commander.js + types | Variable |
| Rust       | ✅ Production | Clap | High performance |

## Advanced Features

### Universal Template System
Universal templates are now always enabled for consistent cross-language generation:
```bash
goobits build
```

### Interactive Mode
Generated CLIs include interactive mode support (varies by language).

### Shell Completion
Automatic shell completion generation for bash, zsh, and fish.

### Performance Optimization
- Lazy loading for advanced features
- <100ms startup times
- <2MB memory usage

## Examples

Working examples are available in the repository:
- `examples/basic-demos/` - Multi-language CLI examples for new users
- `examples/advanced-features/` - Advanced nested command demonstrations
- `goobits.yaml` - Self-hosting configuration (the framework generates its own CLI)

## Support

- **Issues**: [GitHub Issues](https://github.com/goobits/cli/issues)
- **Troubleshooting**: [Common problems and solutions](troubleshooting.md)
- **Configuration**: [Complete reference](configuration.md)