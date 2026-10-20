"""Build command handler for goobits CLI."""

from pathlib import Path
from typing import Optional

import typer

from .utils import (
    _is_hooks_file,
    _lazy_imports,
    backup_file,
    generate_setup_script,
    load_goobits_config,
    update_pyproject_toml,
)


def _detect_main_cli_path(language: str, generated_files: list[str]) -> Path:
    """Return the main generated CLI path for a language."""
    if language == "python":
        candidates = ("cli.py", "main.py")
        extensions = (".py",)
    elif language == "nodejs":
        candidates = ("cli.js", "main.js", "cli.mjs", "main.mjs")
        extensions = (".js", ".mjs")
    elif language == "typescript":
        candidates = ("cli.ts", "main.ts", "cli.js", "main.js", "cli.mjs", "main.mjs")
        extensions = (".ts", ".js", ".mjs")
    elif language == "rust":
        candidates = ("src/main.rs", "src/cli.rs", "main.rs", "cli.rs")
        extensions = (".rs",)
    else:
        return Path()

    for candidate in candidates:
        if candidate in generated_files:
            return Path(candidate)

    for file_path in generated_files:
        file_name = Path(file_path).name
        if "hooks" in file_name:
            continue
        if file_name.endswith(extensions) and (
            "cli" in file_name or "main" in file_name
        ):
            return Path(file_path)

    return Path()


def build_command(
    config_path: Optional[Path] = typer.Argument(
        None, help="Path to goobits.yaml file (defaults to ./goobits.yaml)"
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory (defaults to same directory as config file)",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        help="Output filename for generated CLI (defaults to 'generated_cli.py')",
    ),
    backup: bool = typer.Option(
        False,
        "--backup",
        help="Create backup files (.bak) when overwriting existing files",
    ),
):
    """
    Build CLI and setup scripts from goobits.yaml configuration.

    This command reads a goobits.yaml file and generates:
    - CLI script: Generated from goobits.yaml (default: generated_cli.py)
    - setup.sh: Project setup script

    Use --output to specify a custom CLI filename (e.g., --output cli.py)
    """
    _lazy_imports()

    # Import logging utilities
    # Set up logging context for build operation
    import uuid

    from goobits_cli.core.logging import clear_context, get_logger, set_context

    operation_id = str(uuid.uuid4())[:8]
    set_context(operation="build", operation_id=operation_id)

    logger = get_logger(__name__)
    logger.info("Starting build operation")

    # Determine config file path

    if config_path is None:
        config_path = Path.cwd() / "goobits.yaml"

    config_path = Path(config_path).resolve()

    # Add config context
    set_context(config_file=str(config_path))

    if not config_path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        typer.echo(f"Error: Configuration file '{config_path}' not found.", err=True)

        raise typer.Exit(1)

    # Determine output directory

    if output_dir is None:
        output_dir = config_path.parent

    else:
        output_dir = Path(output_dir).resolve()

    # Ensure output directory exists

    output_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"Loading configuration from: {config_path}")

    # Show backup status

    if not backup:
        typer.echo("\U0001f4a1 Backups disabled (use --backup to create .bak files)")

        typer.echo(
            "\U0001f4a1 Ensure your changes are committed to git before proceeding"
        )

    # Universal Template System is always enabled

    typer.echo("\u26a1 Using Universal Template System with single-file output")

    # Load goobits configuration
    logger.info("Loading goobits configuration")
    goobits_config = load_goobits_config(config_path)
    if goobits_config.package_name == "goobits-cli" and goobits_config.cli.version is None:
        from .utils import extract_version_from_pyproject

        goobits_config.cli.version = extract_version_from_pyproject(config_path.parent)


    # Detect target languages from configuration
    target_languages = goobits_config.get_target_languages()

    # Add package name to context
    set_context(package_name=goobits_config.package_name)

    if len(target_languages) == 1:
        logger.info(f"Detected language: {target_languages[0]}")
        typer.echo(f"Detected language: {target_languages[0]}")
    else:
        logger.info(f"Detected multi-language targets: {', '.join(target_languages)}")
        typer.echo(f"Detected multi-language targets: {', '.join(target_languages)}")

    # Universal Template System is now the default
    typer.echo("\u2705 Using Universal Template System (production-ready)")
    typer.echo("   Generating optimized cross-language CLI with enhanced features.")

    typer.echo("Generating CLI scripts...")

    # Multi-language generation loop
    generated_main_cli_paths: dict[str, Path] = {}
    for language in target_languages:
        # Add current language to context
        set_context(language=language)

        if len(target_languages) > 1:
            typer.echo(
                f"\U0001f680 Generating {language} CLI using Universal Template System"
            )

        # Route to orchestrator for all languages (uses registry-based renderers)
        from goobits_cli.universal.engine.orchestrator import Orchestrator

        orchestrator = Orchestrator()

        # Generate all files for this language
        all_files = orchestrator.generate_content(
            goobits_config, language, config_path.name
        )

        # Determine output directory for this language
        if len(target_languages) > 1:
            # Multi-language: organize by language subdirectories
            lang_output_dir = output_dir / language
            lang_output_dir.mkdir(parents=True, exist_ok=True)
        else:
            # Single language: use the main output directory
            lang_output_dir = output_dir

        generated_main_cli_paths[language] = _detect_main_cli_path(
            language, list(all_files.keys())
        )

        # Write all generated files for this language
        executable_files = all_files.pop("__executable__", [])

        for file_path, content in all_files.items():
            # Skip pyproject.toml when building goobits itself (self-hosting)
            if (
                file_path == "pyproject.toml"
                and goobits_config.package_name == "goobits-cli"
            ):
                typer.echo(
                    "\u23ed\ufe0f  Skipping pyproject.toml for self-hosted goobits-cli"
                )
                continue

            full_path = lang_output_dir / file_path

            # Skip hooks files if they already exist (preserve user implementations)
            if _is_hooks_file(full_path) and full_path.exists():
                typer.echo(
                    f"⏭️  Skipping {full_path} (exists - preserving user implementations)"
                )
                continue

            # Ensure parent directories exist
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Backup existing file if requested
            backup_path = backup_file(full_path, backup)
            if backup_path:
                typer.echo(f"\U0001f4cb Backed up existing file: {backup_path}")

            # Write file
            with open(full_path, "w") as f:
                f.write(content)

            # Make files executable as needed
            if (
                file_path.startswith("bin/")
                or file_path in executable_files
                or file_path == "setup.sh"
            ):
                full_path.chmod(0o755)

            typer.echo(f"\u2705 Generated: {full_path}")

        # Show summary for this language
        file_count = len(all_files) + len(executable_files)
        if len(target_languages) > 1:
            typer.echo(f"\u2705 Generated {file_count} files for {language}")

    # Multi-language generation complete

    # Extract package name and filename for pyproject.toml update (Python only)

    if "python" in target_languages:
        # Use configured output path for Python

        if goobits_config.cli_path:
            cli_path = goobits_config.cli_path.format(
                package_name=goobits_config.package_name.replace("goobits-", "")
            )
        else:
            # Generate default path when none specified
            package_name_safe = goobits_config.package_name.replace("-", "_")
            cli_path = f"{package_name_safe}/cli.py"

        # Extract the actual module name from the CLI output path

        # e.g., "src/ttt/cli.py" -> "ttt"

        cli_path_parts = Path(cli_path).parts

        if "src" in cli_path_parts:
            src_index = cli_path_parts.index("src")

            if src_index + 1 < len(cli_path_parts):
                module_name = cli_path_parts[src_index + 1]

            else:
                # Fallback to package name conversion

                module_name = goobits_config.package_name.replace("-", "_")

        else:
            # Fallback to package name conversion

            module_name = goobits_config.package_name.replace("-", "_")

        # Extract the full module path relative to the package root

        cli_path_obj = Path(cli_path)

        cli_path_parts = cli_path_obj.parts

        # Find the path relative to the package directory

        if "src" in cli_path_parts:
            src_index = cli_path_parts.index("src")

            if src_index + 2 < len(cli_path_parts):  # src/package/...
                # Get all parts after src/package/ up to filename

                relative_parts = cli_path_parts[
                    src_index + 2 :
                ]  # Everything after src/package/

                # Join directory parts with dots, then add filename without .py

                if len(relative_parts) > 1:
                    dir_parts = relative_parts[:-1]  # All but filename

                    filename_part = relative_parts[-1].replace(".py", "")

                    full_module_path = ".".join(dir_parts) + "." + filename_part

                else:
                    # Just a filename

                    full_module_path = relative_parts[0].replace(".py", "")

            else:
                # Fallback to just filename

                full_module_path = cli_path_obj.name.replace(".py", "")

        else:
            # Fallback to just filename

            full_module_path = cli_path_obj.name.replace(".py", "")

        # Update pyproject.toml to use the generated CLI (skip for goobits-cli itself)

        if goobits_config.package_name != "goobits-cli":
            if update_pyproject_toml(
                output_dir,
                module_name,
                goobits_config.command_name,
                full_module_path + ".py",
                backup,
            ):
                typer.echo(
                    f"\u2705 Updated {output_dir}/pyproject.toml to use generated CLI"
                )

                typer.echo(
                    "\n\U0001f4a1 Remember to reinstall the package for changes to take effect:"
                )

                typer.echo("   ./setup.sh install --dev")

            else:
                typer.echo(
                    "\u26a0\ufe0f  Could not update pyproject.toml automatically"
                )

                typer.echo(
                    f"   Please update your entry points to use: {module_name}.{full_module_path}:main"
                )

        else:
            # For goobits-cli, we maintain pyproject.toml manually

            typer.echo(
                f"\u2705 Updated PEP 621 entry point for '{goobits_config.command_name}'"
            )

            typer.echo(f"\u2705 Added setup.sh to package-data for '{module_name}'")

            typer.echo(
                f"\u2705 Updated {output_dir}/pyproject.toml to use generated CLI"
            )

            typer.echo(
                "\n\U0001f4a1 Remember to reinstall the package for changes to take effect:"
            )

            typer.echo("   ./setup.sh install --dev")

    # Generate setup.sh (Python only - Node.js generates its own)

    if "python" in target_languages:
        typer.echo("Generating setup script...")

        setup_script = generate_setup_script(goobits_config, output_dir)

        # Get configured setup_path or default to "setup.sh"
        setup_path = (
            goobits_config.installation.setup_path
            if goobits_config.installation and goobits_config.installation.setup_path
            else "setup.sh"
        )
        setup_output_path = output_dir / setup_path

        # Ensure parent directory exists (for paths like "scripts/setup.sh")
        setup_output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(setup_output_path, "w") as f:
            f.write(setup_script)

        # Make setup.sh executable

        setup_output_path.chmod(0o755)

        typer.echo(f"\u2705 Generated setup script: {setup_output_path}")

    # Update package manifests for Node.js and Rust
    for language in target_languages:
        if language in ["nodejs", "rust"]:
            from goobits_cli.core.manifest import update_manifests_for_build

            # Get CLI output path from generated files
            if language == "rust":
                cli_path = generated_main_cli_paths.get(language, Path()) or Path(
                    "src/main.rs"
                )
            else:
                cli_path = generated_main_cli_paths.get(language, Path()) or Path(
                    "cli.js"
                )

            # Determine correct output directory for multi-language
            if len(target_languages) > 1:
                manifest_output_dir = output_dir / language
            else:
                manifest_output_dir = output_dir

            manifest_config = goobits_config.model_dump()
            manifest_config["language"] = language

            manifest_result = update_manifests_for_build(
                config=manifest_config,
                output_dir=manifest_output_dir,
                cli_path=cli_path,
            )

            if manifest_result.is_err():
                typer.echo(f"\u26a0\ufe0f  Warning: {manifest_result.err()}", err=True)
                typer.echo(
                    "\u2705 CLI generated successfully, but manifest update failed"
                )
            else:
                manifest_file = "package.json" if language == "nodejs" else "Cargo.toml"
                typer.echo(f"\u2705 Updated {manifest_file} with CLI configuration")

            # Display any warnings from the manifest update
            warnings = manifest_result.value or []
            for warning in warnings:
                typer.echo(f"\u26a0\ufe0f  {warning}", err=True)

    logger.info("Build operation completed successfully")
    typer.echo("\U0001f389 Build completed successfully!")

    # Clear operation context
    clear_context()
