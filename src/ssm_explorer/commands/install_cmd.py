"""
Local Poetry wrapper install/uninstall commands.

These commands let users run `ssm-explorer` from any directory while still
using the Poetry-managed project environment.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Annotated

import typer

from ssm_explorer.config import DEFAULT_CONFIG_FILE, DEFAULT_CONFIG_TEMPLATE
from ssm_explorer.display import print_error, print_info, print_success, print_warning

APP_NAME = "ssm-explorer"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"


def _display_path(path: Path) -> str:
    try:
        return str(path.expanduser().resolve()).replace(str(Path.home()), "~", 1)
    except RuntimeError:
        return str(path)


def _validate_project_dir(project_dir: Path) -> Path:
    resolved = project_dir.expanduser().resolve()
    pyproject = resolved / "pyproject.toml"
    if not pyproject.exists():
        raise ValueError(f"Poetry project not found: {_display_path(pyproject)}")
    return resolved


def _wrapper_content(project_dir: Path) -> str:
    return (
        "#!/usr/bin/env sh\n"
        "set -eu\n"
        f'exec poetry -C "{project_dir}" run {APP_NAME} "$@"\n'
    )


def install_command(
    project_dir: Annotated[
        Path | None,
        typer.Option(
            "--project-dir",
            help="Poetry project directory. Defaults to current directory.",
            metavar="DIR",
        ),
    ] = None,
    bin_dir: Annotated[
        Path,
        typer.Option(
            "--bin-dir",
            help="Directory for the wrapper script.",
            metavar="DIR",
        ),
    ] = DEFAULT_BIN_DIR,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="Overwrite an existing wrapper."),
    ] = False,
    init_config: Annotated[
        bool,
        typer.Option(
            "--init-config/--no-init-config",
            help="Create default config if it does not exist.",
        ),
    ] = True,
) -> None:
    """
    Install a local wrapper so `ssm-explorer` works from any directory.

    Run this from the repository root:

        poetry run ssm-explorer install
    """
    target_project = _validate_project_dir(project_dir or Path.cwd())
    target_bin_dir = bin_dir.expanduser()
    wrapper = target_bin_dir / APP_NAME

    if shutil.which("poetry") is None:
        print_error("Poetry executable not found on PATH.")
        raise typer.Exit(code=1)

    if wrapper.exists() and not force:
        print_warning(
            f"Wrapper already exists: {_display_path(wrapper)}\n"
            "Use --force to overwrite it."
        )
        raise typer.Exit(code=0)

    try:
        target_bin_dir.mkdir(parents=True, exist_ok=True)
        wrapper.write_text(_wrapper_content(target_project), encoding="utf-8")
        wrapper.chmod(wrapper.stat().st_mode | 0o755)
    except OSError as exc:
        print_error(f"Could not install wrapper: {exc}")
        raise typer.Exit(code=1) from exc

    print_success(f"Installed wrapper: {_display_path(wrapper)}")
    print_info(f"Project: {_display_path(target_project)}")

    if init_config:
        if DEFAULT_CONFIG_FILE.exists():
            print_info(f"Config exists: {_display_path(DEFAULT_CONFIG_FILE)}")
        else:
            try:
                DEFAULT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
                DEFAULT_CONFIG_FILE.write_text(DEFAULT_CONFIG_TEMPLATE, encoding="utf-8")
            except OSError as exc:
                print_error(f"Could not create config: {exc}")
                raise typer.Exit(code=1) from exc
            print_success(f"Config created: {_display_path(DEFAULT_CONFIG_FILE)}")

    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if str(target_bin_dir) not in path_parts:
        print_warning(
            f"{_display_path(target_bin_dir)} is not on PATH.\n"
            f"Add this to your shell profile: export PATH=\"{_display_path(target_bin_dir)}:$PATH\""
        )


def uninstall_command(
    bin_dir: Annotated[
        Path,
        typer.Option(
            "--bin-dir",
            help="Directory containing the wrapper script.",
            metavar="DIR",
        ),
    ] = DEFAULT_BIN_DIR,
    remove_config: Annotated[
        bool,
        typer.Option(
            "--remove-config",
            help="Also remove ~/.config/ssm-explorer/config.toml.",
        ),
    ] = False,
) -> None:
    """
    Remove the local wrapper installed by `ssm-explorer install`.

    Config is kept unless --remove-config is passed.
    """
    wrapper = bin_dir.expanduser() / APP_NAME

    if wrapper.exists():
        try:
            wrapper.unlink()
        except OSError as exc:
            print_error(f"Could not remove wrapper: {exc}")
            raise typer.Exit(code=1) from exc
        print_success(f"Removed wrapper: {_display_path(wrapper)}")
    else:
        print_warning(f"Wrapper not found: {_display_path(wrapper)}")

    if remove_config:
        if DEFAULT_CONFIG_FILE.exists():
            try:
                DEFAULT_CONFIG_FILE.unlink()
            except OSError as exc:
                print_error(f"Could not remove config: {exc}")
                raise typer.Exit(code=1) from exc
            print_success(f"Removed config: {_display_path(DEFAULT_CONFIG_FILE)}")
        else:
            print_warning(f"Config not found: {_display_path(DEFAULT_CONFIG_FILE)}")
