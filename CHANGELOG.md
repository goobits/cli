# Changelog

All notable changes to the Goobits CLI Framework will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.2.0] - 2026-10-20

### Added
- Conformance reports every manifest problem in one run and runs independent checks.
- Legacy CLIs can declare exit code 1 during adoption, with a deprecation warning.

### Changed
- Unusable declarations are reported and their checks are skipped.

## [3.1.0] - 2026-10-20

### Added
- `goobits conformance check` and a conformance manifest schema for checking CLI behavior.
- The Goobits CLI standard document.

### Changed
- Repository moved to https://github.com/goobits/cli. The PyPI name `goobits-cli` and `goobits` command are unchanged.

### Fixed
- Regenerated self-hosted outputs now match the generator.
- The missing-CLI-section validation test checks the error output correctly.

## [3.0.1] - 2025-08-26

### 🎉 FILE CONSOLIDATION RELEASE

### Added
- **File Consolidation**: Minimal file generation (2-3 files per language)
- **validate command**: Validate goobits.yaml without generating files
- **Script entry point**: Added `goobits` command to pyproject.toml for direct CLI access

### Changed
- **BREAKING**: Generated file structure reduced by 60-93%
  - Python: 2 files (cli.py with embedded utilities, setup.sh)
  - Node.js: 2 files (cli.mjs ES6 module, setup.sh)
  - TypeScript: 3 files (cli.ts, types.d.ts, setup.sh)
  - Rust: 2 files (src/main.rs with inline modules, setup.sh)

### Fixed
- **Critical**: No more README.md generation (preserves user documentation)
- **Critical**: Smart manifest merging (preserves package.json/Cargo.toml)
- **Critical**: Files generated relative to goobits.yaml location
- Documentation accuracy sync with codebase

## [3.0.0] - 2025-08-26

### 🚀 PRODUCTION RELEASE

This is the first official production release of Goobits CLI Framework. The framework is now stable and ready for widespread use.

### Changed
- **Version Bump**: Updated from 3.0.0-beta.1 to 3.0.0 - now production ready
- All version references updated across the codebase

### Production Readiness
- ✅ Core framework: All 4 languages (Python, Node.js, TypeScript, Rust) fully working
- ✅ Test suite: Comprehensive test coverage with consistent pass rates
- ✅ Documentation: Complete and accurate
- ✅ Performance: Optimized with <100ms startup times
- ✅ Stability: All known issues resolved

## [3.0.0-beta.1] - 2025-08-25

### 🚀 PRODUCTION READY BETA RELEASE

### Fixed
- **Critical**: Fixed hanging integration tests in `test_cross_language.py` by adding timeouts and Rust availability checks
- **Critical**: pyproject.toml corrected from misconfigured "final-test-cli" to proper "goobits-cli" package name
- **Critical**: Removed documentation references to non-existent `--universal-templates` flag (Universal Template System is always enabled)
- **Critical**: Added pytest-timeout dependency and proper timeout markers for integration tests
- Fixed test_permission_scenarios.py to check for universal_engine initialization before mocking
- Updated version references in test files from "2.0.0" to "3.0.0" for consistency
- README configuration example now includes required `cli.version` field to match schema requirements
- README development commands section reordered with `validate` command listed first as it's most commonly used
- pyproject.toml testpaths now correctly points to `src/tests/` instead of `tests/`
- CODEMAP.md generator file count corrected from "76 Python files" to "4 generator files + __init__.py"
- Completed comprehensive documentation accuracy review - all CLI commands, API references, configuration examples, and installation instructions verified against codebase
- README Quick Start examples corrected to include required arguments (`goobits init <project_name>` and `goobits build <config_path>`)
- README command documentation updated to show `upgrade` command exists in both generated CLI and development CLI
- README hook implementation section clarified that hook files are not auto-generated and must be created manually
- README command arguments changed from optional `[arg]` to required `<arg>` notation where appropriate

### Added
- **Production Features**: Added ruff linter configuration for CI/CD consistency
- **Production Features**: Added pytest-timeout with proper timeout markers for integration tests
- **Production Features**: Added intelligent Rust compilation skipping when cargo unavailable

### Changed
- **Version Bump**: Updated from 3.0.0-alpha.1 to 3.0.0-beta.1 - approaching production readiness
- **Test Infrastructure**: Integration tests now skip Rust compilation if cargo not available (prevents CI hangs)
- **Test Infrastructure**: Reduced Rust build timeout from 300s to 120s for faster CI feedback
- Documentation sync and accuracy improvements across all markdown files
- Universal Template System is now always enabled (removed non-existent flag references)

### Production Readiness
- ✅ Core framework: All 4 languages working
- ✅ Test suite: Unit tests pass consistently
- ✅ Integration tests: Fixed timeout issues, now stable
- ✅ Documentation: Accurate and comprehensive
- ✅ CI/CD: Proper linting and testing pipeline
- ✅ Version management: Consistent across all components

## [3.0.0-alpha.1] - 2024-12

### 🚀 MAJOR RELEASE - Production Ready

This release delivers full multi-language support with unlimited nested commands and production-ready performance.

### Added
- **Unlimited nested commands** - Support for deep command hierarchies (6+ levels tested)
- **Full Rust support** with Clap framework integration
- **Universal Template System** for consistent cross-language generation
- **Interactive mode** for all generated CLIs
- **Shell completions** for bash, zsh, and fish
- **Performance optimization** achieving <100ms startup times

### Changed
- **Template system** unified across all languages
- **Hook signatures** standardized for better consistency
- **Setup scripts** enhanced with progress tracking and validation

### Fixed
- **Node.js dependency resolution** error messages
- **TypeScript compilation** configuration
- **Rust unused variable warnings** in generated code
- **Test suite stability** - comprehensive test coverage across 55 test files

## [1.x] - Previous Versions

Previous versions focused on foundational Python implementation and initial multi-language support. See git history for detailed changes.