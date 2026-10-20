# Contributing to Goobits CLI Framework

Thank you for your interest in contributing to Goobits CLI Framework! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

Please be respectful and constructive in all interactions. We aim to maintain a welcoming and inclusive community.

## How to Contribute

### Reporting Issues

1. Check existing issues to avoid duplicates
2. Use issue templates when available
3. Provide clear reproduction steps
4. Include relevant system information

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes
4. Add/update tests as needed
5. Ensure all tests pass
6. Update documentation
7. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.8 or higher
- Git
- Virtual environment tool (venv, virtualenv, etc.)

### Local Development

```bash
# Clone the repository
git clone https://github.com/goobits/cli
cd goobits-cli

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .[dev,test]

# Run tests
pytest

# Run linting
black --check src/
flake8 src/

# Type checking
mypy src/goobits_cli/
```

## Testing

### Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest src/tests/unit/

# Integration tests
pytest src/tests/integration/

# With coverage
pytest --cov=goobits_cli
```

### Writing Tests

- Place unit tests in `src/tests/unit/`
- Place integration tests in `src/tests/integration/`
- Use descriptive test names
- Include docstrings explaining test purpose
- Test both success and failure cases

## Code Style

### Python Code

- Follow PEP 8
- Use type hints where appropriate
- Maximum line length: 88 characters (Black default)
- Use meaningful variable names

### Formatting

```bash
# Format code with black
black src/

# Check with flake8
flake8 src/

# Type checking
mypy src/goobits_cli/
```

## Documentation

### Docstrings

Use Google-style docstrings:

```python
def example_function(param1: str, param2: int) -> bool:
    """Brief description of function.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When invalid input provided
    """
```

### README Updates

Update README.md when:
- Adding new features
- Changing configuration schema
- Modifying installation procedures

## Pull Request Process

1. **Before Submitting**
   - Ensure all tests pass
   - Update documentation
   - Add entry to CHANGELOG.md
   - Resolve any merge conflicts

2. **PR Description**
   - Describe what changes were made
   - Explain why changes were necessary
   - Link related issues
   - Include screenshots for UI changes

3. **Review Process**
   - Address reviewer feedback
   - Keep PR focused on single concern
   - Be patient and respectful

## Release Process

Releases are managed by maintainers:

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create git tag
4. Build and publish to PyPI

## Language-Specific Contributions

### Python Generator

- Location: `src/goobits_cli/generators/python.py`
- Templates: `src/goobits_cli/templates/`

### Node.js Generator

- Location: `src/goobits_cli/generators/nodejs.py`
- Templates: `src/goobits_cli/templates/nodejs/`

### TypeScript Generator

- Location: `src/goobits_cli/generators/typescript.py`
- Templates: `src/goobits_cli/templates/typescript/`

### Rust Generator

- Location: `src/goobits_cli/generators/rust.py`
- Templates: `src/goobits_cli/templates/rust/`

## Universal Template System

When contributing to the Universal Template System:

- Location: `src/goobits_cli/universal/`
- Ensure cross-language compatibility
- Test with all supported languages
- Update renderers as needed

## Performance Considerations

- Run performance benchmarks: `python performance/benchmark_suite.py`
- Target: <100ms startup time
- Keep memory usage minimal
- Use lazy loading where appropriate

## Questions?

- Open a GitHub Discussion for general questions
- Join our community chat (if available)
- Check existing documentation

Thank you for contributing to Goobits CLI Framework!