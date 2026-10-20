"""Shared utilities for command handlers."""

import json
import shutil
from pathlib import Path
from typing import Optional

import typer

# Lazy imports for heavy dependencies
yaml = None
toml = None
Environment = None
FileSystemLoader = None
ValidationError = None
GoobitsConfigSchema = None
deepcopy = None


def _lazy_imports():
    """Load heavy dependencies only when needed."""
    global yaml, toml, Environment, FileSystemLoader, ValidationError
    global GoobitsConfigSchema, deepcopy

    if yaml is None:
        import yaml as _yaml

        yaml = _yaml
    if toml is None:
        import toml as _toml

        toml = _toml
    if Environment is None:
        from jinja2 import (
            Environment as _Environment,
        )
        from jinja2 import (
            FileSystemLoader as _FileSystemLoader,
        )

        Environment = _Environment
        FileSystemLoader = _FileSystemLoader
    if ValidationError is None:
        from pydantic import ValidationError as _ValidationError

        ValidationError = _ValidationError
    if GoobitsConfigSchema is None:
        from goobits_cli.core.schemas import GoobitsConfigSchema as _GoobitsConfigSchema

        GoobitsConfigSchema = _GoobitsConfigSchema
    if deepcopy is None:
        from copy import deepcopy as _deepcopy

        deepcopy = _deepcopy


# Default cache time-to-live in seconds (1 hour)
DEFAULT_CACHE_TTL = 3600


def _is_hooks_file(path: Path) -> bool:
    """Check if a file is a hooks file that should be preserved."""
    name = path.name.lower()
    return "hooks" in name and name.endswith(".py")


def load_goobits_config(file_path: Path) -> "GoobitsConfigSchema":
    """Load and validate goobits.yaml configuration file."""
    _lazy_imports()

    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)

        config = GoobitsConfigSchema(**data)

        return config

    except FileNotFoundError:
        typer.echo(f"Error: File '{file_path}' not found.", err=True)

        raise typer.Exit(1)

    except yaml.YAMLError as e:
        # Extract line number and provide helpful context
        error_msg = str(e)
        if hasattr(e, "problem_mark"):
            mark = e.problem_mark
            error_msg = (
                f"\n{chr(10060)} YAML Parsing Error at line {mark.line + 1}, column {mark.column + 1}:\n"
                f"   {e.problem}\n"
            )
            if e.context:
                error_msg += f"   Context: {e.context}\n"

            # Try to show the problematic line
            try:
                with open(file_path) as f:
                    lines = f.readlines()
                    if 0 <= mark.line < len(lines):
                        error_msg += (
                            f"\n   Line {mark.line + 1}: {lines[mark.line].rstrip()}\n"
                        )
                        error_msg += "   " + " " * mark.column + "^\n"
            except (AttributeError, IndexError):
                # Ignore errors when trying to format YAML error details
                pass

            error_msg += "\n{chr(128161)} Tip: Check that indentation is consistent (use 2 spaces, not tabs)"
        else:
            error_msg = f"\n{chr(10060)} YAML Parsing Error: {e}\n"
            error_msg += (
                "\n{chr(128161)} Tip: Validate your YAML at https://yamlchecker.com/"
            )

        typer.echo(error_msg, err=True)
        raise typer.Exit(1)

    except ValidationError as e:
        # Format validation errors more helpfully
        error_msg = "\n{chr(10060)} Configuration Validation Errors:\n"

        for error in e.errors():
            field_path = ".".join(str(x) for x in error["loc"])
            error_type = error["type"]
            msg = error["msg"]

            error_msg += f"\n   {chr(8226)} Field '{field_path}': {msg}\n"

            # Add helpful suggestions based on error type
            if "missing" in error_type:
                error_msg += (
                    "     {chr(128161)} Add this required field to your configuration\n"
                )
            elif "choice" in error_type or "enum" in error_type:
                if "ctx" in error and "enum_values" in error["ctx"]:
                    valid_values = error["ctx"]["enum_values"]
                    error_msg += f"     {chr(128161)} Valid values: {', '.join(map(str, valid_values))}\n"
            elif "type" in error_type:
                error_msg += f"     {chr(128161)} Expected type: {error_type.replace('type_error.', '')}\n"

        error_msg += "\n{chr(128214)} See examples at: https://github.com/goobits/cli#quick-start\n"

        typer.echo(error_msg, err=True)
        raise typer.Exit(1)


def normalize_dependencies_for_template(
    config: "GoobitsConfigSchema",
) -> "GoobitsConfigSchema":
    """Return config unchanged (dependencies are normalized by schema)."""
    _lazy_imports()
    return deepcopy(config)


def dependency_to_dict(dep):
    """Convert DependencyItem to dict for JSON serialization."""

    if isinstance(dep, str):
        return {"name": dep, "type": "command"}

    elif hasattr(dep, "model_dump"):
        return dep.model_dump()

    elif hasattr(dep, "dict"):
        return dep.dict()

    elif isinstance(dep, dict):
        return dep

    else:
        return {"name": str(dep), "type": "command"}


def dependencies_to_json(deps):
    """Convert list of dependencies to JSON string."""

    return json.dumps([dependency_to_dict(dep) for dep in deps])


def extract_version_from_pyproject(project_dir: Path) -> str:
    """Extract version from pyproject.toml."""
    _lazy_imports()

    pyproject_path = project_dir / "pyproject.toml"

    if not pyproject_path.exists():
        return "unknown"

    try:
        with open(pyproject_path) as f:
            data = toml.load(f)

        # Try different locations for version

        if (
            "tool" in data
            and "poetry" in data["tool"]
            and "version" in data["tool"]["poetry"]
        ):
            return data["tool"]["poetry"]["version"]

        elif "project" in data and "version" in data["project"]:
            return data["project"]["version"]

        else:
            return "unknown"

    except Exception:
        return "unknown"


def generate_setup_script(config: "GoobitsConfigSchema", project_dir: Path) -> str:
    """Generate setup.sh script from goobits configuration."""
    _lazy_imports()

    # Use universal components directory for templates
    template_dir = Path(__file__).parent.parent / "universal" / "components"

    env = Environment(
        loader=FileSystemLoader(template_dir), trim_blocks=True, lstrip_blocks=True
    )

    # Add custom filters
    env.filters["dependency_to_dict"] = dependency_to_dict
    env.filters["dependencies_to_json"] = dependencies_to_json

    template = env.get_template("setup_template_python.j2")

    # Extract version from pyproject.toml

    version = extract_version_from_pyproject(project_dir)

    # Convert goobits config to template variables

    template_vars = {
        "package_name": config.package_name,
        "command_name": config.command_name,
        "display_name": config.display_name,
        "description": config.description,
        "version": version,
        "python": {
            "minimum_version": config.python.minimum_version,
            "maximum_version": config.python.maximum_version,
        },
        "dependencies": {
            "required": config.dependencies.required,
            "optional": config.dependencies.optional,
        },
        "installation": {
            "pypi_name": (
                config.installation.pypi_name
                if config.installation
                else config.package_name
            ),
            "development_path": (
                config.installation.development_path if config.installation else "."
            ),
            "extras": config.installation.extras if config.installation else {},
        },
        "shell_integration": {
            "enabled": (
                config.shell_integration.enabled if config.shell_integration else False
            ),
            "alias": (
                config.shell_integration.alias
                if config.shell_integration
                else config.command_name
            ),
        },
        "validation": {
            "check_api_keys": (
                config.validation.check_api_keys if config.validation else False
            ),
            "check_disk_space": (
                config.validation.check_disk_space if config.validation else True
            ),
            "minimum_disk_space_mb": (
                config.validation.minimum_disk_space_mb if config.validation else 100
            ),
        },
        "messages": {
            "install_success": (
                config.messages.install_success
                if config.messages
                else "Installation completed successfully!"
            ),
            "install_dev_success": (
                config.messages.install_dev_success
                if config.messages
                else "Development installation completed successfully!"
            ),
            "upgrade_success": (
                config.messages.upgrade_success
                if config.messages
                else "Upgrade completed successfully!"
            ),
            "uninstall_success": (
                config.messages.uninstall_success
                if config.messages
                else "Uninstall completed successfully!"
            ),
        },
        "cache_ttl": DEFAULT_CACHE_TTL,
    }

    script = template.render(**template_vars)

    return script


def backup_file(file_path: Path, create_backup: bool = False) -> Optional[Path]:
    """Create a backup of a file if it exists and backup is requested."""

    if create_backup and file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")

        shutil.copy2(file_path, backup_path)

        return backup_path

    return None


def update_pyproject_toml(
    project_dir: Path,
    package_name: str,
    command_name: str,
    cli_filename: str = "generated_cli.py",
    create_backup: bool = False,
) -> bool:
    """Update pyproject.toml to use the generated CLI."""
    _lazy_imports()

    pyproject_path = project_dir / "pyproject.toml"

    if not pyproject_path.exists():
        typer.echo(
            "[warn]  No pyproject.toml found, skipping entry point update", err=True
        )

        return False

    try:
        # Backup pyproject.toml if requested

        backup_path = backup_file(pyproject_path, create_backup)

        if backup_path:
            typer.echo(f"[backup] Created backup: {backup_path}")

        # Read pyproject.toml

        with open(pyproject_path) as f:
            data = toml.load(f)

        # Update the entry points

        # Remove .py extension from filename for module import

        cli_module_name = cli_filename.replace(".py", "")

        if (
            "tool" in data
            and "poetry" in data["tool"]
            and "scripts" in data["tool"]["poetry"]
        ):
            # Poetry format

            data["tool"]["poetry"]["scripts"][
                command_name
            ] = f"{package_name}.{cli_module_name}:main"

            typer.echo(f"[check] Updated Poetry entry point for '{command_name}'")

        elif "project" in data and "scripts" in data["project"]:
            # PEP 621 format
            # Convert package name hyphens to underscores for Python module naming
            module_name = package_name.replace("-", "_")
            data["project"]["scripts"][
                command_name
            ] = f"{module_name}.{cli_module_name}:main"

            typer.echo(f"[check] Updated PEP 621 entry point for '{command_name}'")

        else:
            # Create project.scripts section if it doesn't exist

            if "project" not in data:
                data["project"] = {}

            if "scripts" not in data["project"]:
                data["project"]["scripts"] = {}

            # Convert package name hyphens to underscores for Python module naming
            module_name = package_name.replace("-", "_")
            data["project"]["scripts"][
                command_name
            ] = f"{module_name}.{cli_module_name}:main"

            typer.echo(f"[check] Created entry point for '{command_name}'")

        # Add package-data configuration for setup.sh

        if "project" in data:  # PEP 621 format
            if "tool" not in data:
                data["tool"] = {}

            if "setuptools" not in data["tool"]:
                data["tool"]["setuptools"] = {}

            if "package-data" not in data["tool"]["setuptools"]:
                data["tool"]["setuptools"]["package-data"] = {}

            # Add setup.sh to package-data
            # Convert package name hyphens to underscores for Python module naming
            module_name = package_name.replace("-", "_")

            if module_name not in data["tool"]["setuptools"]["package-data"]:
                data["tool"]["setuptools"]["package-data"][module_name] = ["setup.sh"]

                typer.echo(
                    f"[check] Added setup.sh to package-data for '{module_name}'"
                )

            else:
                existing = data["tool"]["setuptools"]["package-data"][module_name]

                if isinstance(existing, list) and "setup.sh" not in existing:
                    existing.append("setup.sh")

                    typer.echo(
                        f"[check] Added setup.sh to existing package-data for '{module_name}'"
                    )

                elif isinstance(existing, str) and existing != "setup.sh":
                    # Convert single string to list and add setup.sh

                    data["tool"]["setuptools"]["package-data"][module_name] = [
                        existing,
                        "setup.sh",
                    ]

                    typer.echo(
                        f"[check] Added setup.sh to existing package-data for '{module_name}'"
                    )

                elif "setup.sh" in existing or existing == "setup.sh":
                    typer.echo(
                        f"[info]  setup.sh already in package-data for '{module_name}'"
                    )

        elif "tool" in data and "poetry" in data["tool"]:
            # Poetry format - handle includes differently

            if "packages" not in data["tool"]["poetry"]:
                data["tool"]["poetry"]["packages"] = []

            # Poetry uses include for additional files

            if "include" not in data["tool"]["poetry"]:
                data["tool"]["poetry"]["include"] = []

            # Add setup.sh to includes if not already present

            setup_include = {"path": "setup.sh", "format": "sdist"}

            if setup_include not in data["tool"]["poetry"]["include"]:
                data["tool"]["poetry"]["include"].append(setup_include)

                typer.echo(
                    f"[check] Added setup.sh to Poetry includes for '{package_name}'"
                )

            else:
                typer.echo(
                    f"[info]  setup.sh already in Poetry includes for '{package_name}'"
                )

        # Write back the modified pyproject.toml

        with open(pyproject_path, "w") as f:
            toml.dump(data, f)

        return True

    except Exception as e:
        typer.echo(f"[error] Error updating pyproject.toml: {e}", err=True)

        return False
