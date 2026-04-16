"""Bluray Vault CLI — command-line and interactive interface."""

from __future__ import annotations

import click

from src.cli.app import interactive_loop
from src.core.volume import init_volume, list_volumes, load_volume
from src.core.workflow import (
    add_files,
    burn_volume,
    recover_volume,
    status_volume,
    verify_volume,
)
from src.models.schemas import RedundancyLevel


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """Bluray Vault — archival backup with extreme recoverability."""
    if ctx.invoked_subcommand is None:
        interactive_loop()


@main.command()
@click.argument("volume")
@click.option(
    "--redundancy", "-R",
    type=click.Choice(["standard", "high", "extreme"]),
    default="high",
    help="Redundancy level (default: high)",
)
def init(volume: str, redundancy: str) -> None:
    """Initialize a new backup volume."""
    level = RedundancyLevel(redundancy)
    meta = init_volume(volume, redundancy=level)
    click.echo(f"Volume '{volume}' created ({level.value}: "
               f"{meta.erasure.data_stripes}+{meta.erasure.parity_stripes})")


@main.command()
@click.argument("volume")
@click.argument("files", nargs=-1, required=True)
def add(volume: str, files: tuple[str, ...]) -> None:
    """Add files to a volume's staging area."""
    count = add_files(volume, list(files))
    click.echo(f"Staged {count} file(s) to '{volume}'")


@main.command()
@click.argument("volume")
@click.option("--passphrase", "-p", default="", help="Encryption passphrase")
def burn(volume: str, passphrase: str) -> None:
    """Burn staged data to disc(s)."""
    discs = burn_volume(volume, passphrase=passphrase)
    if discs:
        click.echo(f"Burned {len(discs)} disc(s)")


@main.command(name="verify")
@click.argument("volume")
@click.option("--disc", "disc_index", type=int, default=None, help="Verify specific disc")
def verify_cmd(volume: str, disc_index: int | None) -> None:
    """Verify disc integrity."""
    ok = verify_volume(volume, disc_index=disc_index)
    click.echo("Verification " + ("passed" if ok else "FAILED"))


@main.command()
@click.argument("volume")
@click.argument("output")
@click.option("--passphrase", "-p", default="", help="Decryption passphrase")
def recover(volume: str, output: str, passphrase: str) -> None:
    """Recover data from disc set to output directory."""
    success = recover_volume(volume, output, passphrase=passphrase)
    click.echo("Recovery " + ("complete" if success else "failed"))


@main.command()
@click.argument("volume")
def status(volume: str) -> None:
    """Show volume and disc status."""
    status_volume(volume)


@main.command(name="list")
def list_cmd() -> None:
    """List all volumes."""
    volumes = list_volumes()
    if not volumes:
        click.echo("No volumes found")
        return
    for v in volumes:
        click.echo(f"  {v}")


if __name__ == "__main__":
    main()
