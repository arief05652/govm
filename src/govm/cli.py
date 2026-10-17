"""Click CLI for govm."""

from __future__ import annotations

import click

from . import core


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="govm")
def cli() -> None:
    """govm - manage multiple Go toolchain versions."""


@cli.command(short_help="Install a Go version.")
@click.argument("version")
@click.option("--force", is_flag=True, help="Reinstall even if already present.")
def install(version: str, force: bool) -> None:
    """Install VERSION.

    VERSION accepts either form, e.g. 1.22.0 or go1.22.0.
    """
    try:
        core.install(version, force=force)
    except core.GovmError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"OK: {core.normalize(version)} installed.")
    click.echo(f"Activate it with: govm use {core.normalize(version)}")


@cli.command(name="list")
def list_cmd() -> None:
    """Show installed Go versions."""
    versions = core.installed_versions()
    if not versions:
        click.echo("No versions installed. Try `govm remote` then `govm install <version>`.")
        return

    current = core.current_version()
    for version in versions:
        mark = "*" if version == current else " "
        click.echo(f"{mark} {version.removeprefix('go')}  ({version})")


@cli.command()
@click.argument("version")
@click.option("--no-path", is_flag=True, help="Do not touch the shell rc PATH setup.")
def use(version: str, no_path: bool) -> None:
    """Select VERSION as the active version."""
    try:
        core.use(version, update_path=not no_path)
    except core.GovmError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"OK: now using {core.normalize(version)}")

    rc = core.path_configured()
    if rc is not None:
        click.echo(f"PATH: {core.BIN_DIR} is on PATH via {rc}")
        click.echo("Open a new shell (or re-source that file) for it to take effect.")


@cli.command()
@click.argument("version")
def uninstall(version: str) -> None:
    """Remove an installed VERSION."""
    try:
        core.uninstall(version)
    except core.GovmError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"OK: {core.normalize(version)} removed.")


@cli.command()
@click.option("--all", "show_all", is_flag=True, help="Also show unstable versions (rc/beta).")
@click.option("--limit", default=15, show_default=True, help="Number of rows to show.")
def remote(show_all: bool, limit: int) -> None:
    """Show Go versions available for download."""
    try:
        releases = core.list_releases()
    except core.GovmError as exc:
        raise click.ClickException(str(exc)) from exc

    installed = set(core.installed_versions())
    shown = 0
    for release in releases:
        if not show_all and not release.stable:
            continue
        tag = " [installed]" if release.version in installed else ""
        click.echo(f"{release.short}{tag}")
        shown += 1
        if limit and shown >= limit:
            break


@cli.command()
def current() -> None:
    """Show the active version."""
    version = core.current_version()
    click.echo(version.removeprefix("go") if version else "(no active version)")


@cli.command()
def env() -> None:
    """Show path info and PATH setup."""
    click.echo(core.env_report())


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
