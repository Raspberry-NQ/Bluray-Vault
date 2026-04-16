"""Bluray Vault CLI — command-line and interactive interface."""

from __future__ import annotations

import click

from src.cli.app import interactive_loop
from src.core.volume import init_volume, list_volumes
from src.core.workflow import (
    add_files,
    burn_volume,
    get_volume_status,
    recover_volume,
    verify_volume,
)
from src.models.schemas import RedundancyLevel


def _fmt_redundancy(level: RedundancyLevel) -> str:
    return {
        RedundancyLevel.STANDARD: "Standard 16+4 (20%)",
        RedundancyLevel.HIGH: "High 16+8 (50%)",
        RedundancyLevel.EXTREME: "Extreme 8+8 (100%)",
    }.get(level, str(level))


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
    click.echo(f"Volume '{volume}' created ({_fmt_redundancy(level)})")
    click.echo(f"ID: {meta.volume_id}")


@main.command()
@click.argument("volume")
@click.argument("files", nargs=-1, required=True)
def add(volume: str, files: tuple[str, ...]) -> None:
    """Add files to a volume's staging area."""
    result = add_files(volume, list(files))
    if result.added:
        click.echo(f"Staged {len(result.added)} file(s)")
    if result.skipped_not_found:
        click.echo(f"Skipped (not found): {', '.join(result.skipped_not_found)}")
    if result.skipped_exists:
        click.echo(f"Skipped (already staged): {', '.join(result.skipped_exists)}")


@main.command()
@click.argument("volume")
@click.option("--passphrase", "-p", default="", help="Encryption passphrase")
def burn(volume: str, passphrase: str) -> None:
    """Burn staged data to disc(s)."""
    result = burn_volume(volume, passphrase=passphrase)
    if result.discs:
        for d in result.discs:
            click.echo(f"Disc {d.disc_index} ({d.disc_id}): {d.data_chunks}+{d.parity_chunks} chunks")
        if result.simulated:
            click.echo("(simulated burn)")
    else:
        click.echo("No staged files to burn")


@main.command(name="verify")
@click.argument("volume")
@click.option("--disc", "disc_index", type=int, default=None, help="Verify specific disc")
def verify_cmd(volume: str, disc_index: int | None) -> None:
    """Verify disc integrity."""
    discs = verify_volume(volume, disc_index=disc_index)
    if discs:
        for d in discs:
            click.echo(f"Disc {d.disc_index} ({d.disc_id}): OK (simulated)")
    else:
        click.echo("No discs to verify")


@main.command()
@click.argument("volume")
@click.argument("output")
@click.option("--passphrase", "-p", default="", help="Decryption passphrase")
def recover(volume: str, output: str, passphrase: str) -> None:
    """Recover data from disc set to output directory."""
    meta, total = recover_volume(volume, output, passphrase=passphrase)
    if total > 0:
        click.echo(f"Recovered {total:,} bytes from {len(meta.discs)} disc(s) (simulated)")
    else:
        click.echo("No discs found for recovery")


@main.command()
@click.argument("volume")
def status(volume: str) -> None:
    """Show volume and disc status."""
    meta = get_volume_status(volume)
    click.echo(f"Volume: {meta.name} (id: {meta.volume_id})")
    click.echo(f"Status: {meta.status.value}")
    click.echo(f"Redundancy: {_fmt_redundancy(meta.erasure.redundancy)}")
    click.echo(f"Encryption: {meta.encryption.algorithm}")
    click.echo(f"Discs: {meta.total_discs}")
    for d in meta.discs:
        click.echo(f"  Disc {d.disc_index} ({d.disc_id}): {d.status.value}, "
                    f"{d.data_chunks}+{d.parity_chunks} chunks, "
                    f"{d.total_bytes:,} bytes")


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
