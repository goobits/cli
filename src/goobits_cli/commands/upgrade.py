"""Upgrade command handler for goobits CLI."""

import subprocess
from typing import Optional

import typer

from goobits_cli.__version__ import __version__
from goobits_cli.universal.performance.subprocess_cache import run_cached

from .utils import _lazy_imports


def upgrade_command(
    source: str = typer.Option("pypi", help="Upgrade source: pypi, git, local"),
    version: Optional[str] = typer.Option(None, help="Specific version to install"),
    pre_release: bool = typer.Option(
        False, "--pre", help="Include pre-release versions"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be upgraded without doing it"
    ),
):
    """
    Upgrade goobits-cli to the latest version.

    This command uses pipx to safely upgrade goobits-cli in its isolated environment.
    Multiple upgrade sources are supported for flexibility.

    Sources:
        pypi: Upgrade from PyPI (default)
        git: Upgrade from GitHub repository
        local: Upgrade from current directory (for development)

    Examples:
        goobits upgrade                    # Upgrade from PyPI
        goobits upgrade --version 1.2.0    # Upgrade to specific version
        goobits upgrade --source git       # Upgrade from latest git
        goobits upgrade --dry-run          # See what would be upgraded
    """
    _lazy_imports()

    # Check if pipx is available

    try:
        result = run_cached(
            ["pipx", "--version"], capture_output=True, text=True, check=True
        )

        typer.echo(f"Using pipx version: {result.stdout.strip()}")

    except (subprocess.CalledProcessError, FileNotFoundError):
        typer.echo(
            "\u274c Error: pipx is required for upgrades but not found.", err=True
        )

        typer.echo("Install pipx: https://pypa.github.io/pipx/installation/", err=True)

        raise typer.Exit(1)

    # Get current version

    current_version = __version__

    typer.echo(f"Current version: {current_version}")

    # Build upgrade command based on source

    if source == "pypi":
        if version:
            cmd = ["pipx", "install", f"goobits-cli=={version}", "--force"]

            target_desc = f"version {version} from PyPI"

        else:
            cmd = ["pipx", "upgrade", "goobits-cli"]

            if pre_release:
                cmd.extend(["--pip-args", "--pre"])

            target_desc = "latest version from PyPI"

    elif source == "git":
        git_url = "git+https://github.com/goobits/cli.git"

        if version:
            git_url += f"@{version}"

        cmd = ["pipx", "install", git_url, "--force"]

        target_desc = f"version {version if version else 'latest'} from Git"

    elif source == "local":
        cmd = ["pipx", "install", ".", "--force", "--editable"]

        target_desc = "local development version"

    else:
        typer.echo(
            f"\u274c Error: Unknown source '{source}'. Use: pypi, git, local", err=True
        )

        raise typer.Exit(1)

    typer.echo(f"Planning to upgrade to: {target_desc}")

    if dry_run:
        typer.echo(f"Dry run - would execute: {' '.join(cmd)}")

        return

    # Confirm upgrade

    if not typer.confirm(f"Upgrade goobits-cli to {target_desc}?"):
        typer.echo("Upgrade cancelled.")

        return

    # Execute upgrade

    typer.echo("\U0001f504 Upgrading goobits-cli...")

    try:
        result = run_cached(cmd, capture_output=True, text=True, check=True)

        # Show success message

        typer.echo("\u2705 Upgrade completed successfully!")

        # Try to get new version

        try:
            version_result = run_cached(
                ["goobits", "--version"], capture_output=True, text=True, check=True
            )

            new_version = version_result.stdout.strip().split()[-1]

            if new_version != current_version:
                typer.echo(
                    f"\U0001f4c8 Upgraded from {current_version} \u2192 {new_version}"
                )

            else:
                typer.echo(f"Already at latest version: {current_version}")

        except Exception:
            typer.echo("New version information not available")

        if result.stdout:
            typer.echo("\nInstall output:")

            typer.echo(result.stdout)

    except subprocess.CalledProcessError as e:
        typer.echo(f"\u274c Upgrade failed: {e}", err=True)

        if e.stderr:
            typer.echo(f"Error details: {e.stderr}", err=True)

        # Suggest troubleshooting

        typer.echo("\n\U0001f4a1 Troubleshooting:")

        typer.echo("- Ensure pipx is up to date: pipx upgrade pipx")

        typer.echo("- Check network connection for PyPI/Git access")

        typer.echo("- Try: pipx reinstall goobits-cli")

        raise typer.Exit(1)

    except Exception as e:
        typer.echo(f"\u274c Unexpected error during upgrade: {e}", err=True)

        raise typer.Exit(1)
