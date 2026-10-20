"""Read the source version from pyproject.toml or installed package metadata."""

from importlib.metadata import version
from pathlib import Path

import toml


def _get_version() -> str:
    pyproject_path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if pyproject_path.is_file():
        return str(toml.load(pyproject_path)["project"]["version"])
    return version("goobits-cli")


__version__ = _get_version()
