# Troubleshooting Guide

Common issues and solutions for the Goobits CLI Framework.

## Installation Issues

### Python Environment Conflicts

**Problem**: `pip install` fails with "externally-managed-environment"

**Solution**: Use `pipx` for isolated installation:
```bash
pipx install goobits-cli
```

**Alternative**: Use virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
pip install goobits-cli
```

### Missing Dependencies

**Problem**: `ModuleNotFoundError` when running goobits

**Solution**: Install with development dependencies:
```bash
pip install goobits-cli[dev]
```

## Generation Issues

### Template Not Found Errors

**Problem**: `TemplateNotFound: rust/Cargo.toml.j2`

**Cause**: Missing template files for target language

**Solution**: 
1. Verify language support: `python -c "from goobits_cli.generators import rust; print('Rust supported')"`
2. Check template installation: Look for files in `src/goobits_cli/templates/rust/`
3. Reinstall if needed: `pip install --force-reinstall goobits-cli`

### Universal Template System Issues

**Problem**: Template generation errors

**Solutions**:
- Update to latest version: `pip install --upgrade goobits-cli`
- Universal templates are now always enabled for consistency
- Check component registry: Templates may need regeneration

## Language-Specific Issues

### Node.js CLI Problems

**Problem**: Generated CLI files not executable

**Solution**: Set execute permissions:
```bash
chmod +x bin/cli.js
# or 
chmod +x cli.js
```

**Problem**: `npm install` fails during generation

**Solutions**:
1. Check Node.js version: Requires Node.js 14+
2. Clear npm cache: `npm cache clean --force`
3. Use yarn instead: Install yarn and retry

### TypeScript Compilation Errors

**Problem**: Build fails with TypeScript errors

**Solutions**:
1. Check TypeScript version in generated `package.json`
2. Verify `tsconfig.json` configuration
3. Install dependencies: `npm install`
4. Manual compile test: `npx tsc --noEmit`

**Common Fix**: Update build configuration:
```json
{
  "compilerOptions": {
    "moduleResolution": "node",
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true
  }
}
```

### Rust Compilation Issues

**Problem**: `cargo build` fails in generated project

**Solutions**:
1. Verify Rust installation: `cargo --version`
2. Update Rust: `rustup update`
3. Check Cargo.toml dependencies
4. Manual build test: `cd generated_project && cargo check`

### Python Import Errors

**Problem**: Generated CLI can't import hook functions

**Cause**: Incorrect entry point in `pyproject.toml`

**Solution**: Verify entry point format:
```toml
[project.scripts]
my-cli = "my_cli.cli:main"  # package.module:function
```

## Performance Issues

### Slow CLI Startup

**Expected**: Generated CLIs should start in <100ms

**If slower**:
1. Check for heavy imports in hook files
2. Use lazy imports where possible
3. Profile with: `python -X importtime cli.py --help`

### Memory Usage

**Expected**: <2MB memory usage for basic operations

**If higher**:
1. Check for memory leaks in hook functions
2. Avoid global state in hooks
3. Profile with: `python -m memory_profiler cli.py`

## Configuration Errors

### YAML Syntax Errors

**Problem**: `yaml.scanner.ScannerError`

**Solutions**:
1. Validate YAML syntax: Use online YAML validator
2. Check indentation: Use spaces, not tabs
3. Quote strings with special characters

### Schema Validation Errors

**Problem**: Pydantic validation errors

**Common Issues**:
- Missing required fields (`package_name`, `cli.name`)
- Invalid language choice (must be `python`, `nodejs`, `typescript`, `rust`)
- Incorrect command structure

**Debug**: Run with verbose flag:
```bash
goobits build --verbose goobits.yaml
```

## Build Process Issues

### Permission Denied

**Problem**: Can't write to output directory

**Solutions**:
1. Check directory permissions: `ls -la`
2. Run with sudo (not recommended): `sudo goobits build`
3. Change output directory: `goobits build --output-dir /tmp/cli`

### File Already Exists

**Problem**: Won't overwrite existing files

**Solutions**:
1. Use backup flag: `goobits build --backup`
2. Remove existing files manually
3. Use different output directory

## Testing Generated CLIs

### CLI Doesn't Respond

**Problem**: Generated CLI runs but doesn't work

**Debug Steps**:
1. Test basic functionality: `./cli.py --help`
2. Check hook file syntax: `python -m py_compile cli_hooks.py`
3. Verify entry point: Check `pyproject.toml` or `package.json`
4. Test installation: `./setup.sh install --dev`

### Hook Functions Not Called

**Problem**: CLI runs but hook logic doesn't execute

**Solutions**:
1. Check hook function naming: Must match command names
2. Verify hook file path in `goobits.yaml`
3. Test hook import: `python -c "from cli_hooks import on_command_name"`

## Getting Help

### Enable Verbose Output
```bash
goobits build --verbose goobits.yaml
```

### Check System Requirements
```bash
python --version  # Requires 3.8+
node --version    # Requires 14+ (for Node.js targets)
cargo --version   # Required for Rust targets
```

### Report Issues

If problems persist:
1. Check [GitHub Issues](https://github.com/goobits/cli/issues)
2. Include output of `goobits --version`
3. Provide minimal reproduction case
4. Include error messages and stack traces

### Development Mode

For framework development:
```bash
git clone https://github.com/goobits/cli
cd goobits-cli
./setup.sh install --dev
```

This enables immediate reflection of framework changes.