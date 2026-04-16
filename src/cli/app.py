"""Interactive menu UI for Bluray Vault."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.core.volume import list_volumes
from src.core.workflow import (
    add_files,
    burn_volume,
    recover_volume,
    status_volume,
    verify_volume,
)
from src.models.schemas import RedundancyLevel

console = Console()


def print_banner() -> None:
    banner = Text()
    banner.append("Bluray Vault", style="bold cyan")
    banner.append(" — Archival backup with extreme recoverability", style="dim")
    console.print(Panel(banner, border_style="cyan", padding=(0, 2)))


def print_menu() -> None:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Key", style="bold yellow", width=4)
    table.add_column("Action")
    table.add_row("[n]", "Initialize new volume")
    table.add_row("[a]", "Add files to volume")
    table.add_row("[b]", "Burn volume to disc")
    table.add_row("[v]", "Verify disc integrity")
    table.add_row("[r]", "Recover from disc set")
    table.add_row("[s]", "Show volume status")
    table.add_row("[l]", "List volumes")
    table.add_row("[q]", "Quit")
    console.print(table)


def select_volume(prompt: str = "Select volume") -> str | None:
    volumes = list_volumes()
    if not volumes:
        console.print("[dim]No volumes found. Create one first.[/dim]")
        return None
    if len(volumes) == 1:
        console.print(f"Auto-selected volume: [cyan]{volumes[0]}[/cyan]")
        return volumes[0]
    console.print("Available volumes:")
    for i, v in enumerate(volumes, 1):
        console.print(f"  {i}. {v}")
    choice = console.input("  Choose [1-{}]: ".format(len(volumes)))
    try:
        return volumes[int(choice) - 1]
    except (ValueError, IndexError):
        console.print("[red]Invalid choice.[/red]")
        return None


def do_init() -> None:
    console.print("\n[bold]Initialize New Volume[/bold]")
    name = console.input("  Volume name: ").strip()
    if not name:
        console.print("[red]Name required.[/red]")
        return

    console.print("  Redundancy level:")
    console.print("    1. Standard (16+4, 20% overhead)")
    console.print("    2. High      (16+8, 50% overhead) [default]")
    console.print("    3. Extreme   (8+8,  100% overhead)")
    choice = console.input("  Choose [1-3, default=2]: ").strip()
    levels = {
        "1": RedundancyLevel.STANDARD,
        "2": RedundancyLevel.HIGH,
        "3": RedundancyLevel.EXTREME,
    }
    redundancy = levels.get(choice, RedundancyLevel.HIGH)

    from src.core.volume import init_volume
    try:
        meta = init_volume(name, redundancy=redundancy)
        console.print(f"[green]Volume '{name}' created.[/green]")
        console.print(f"  Redundancy: {redundancy.value} "
                      f"({meta.erasure.data_stripes}+{meta.erasure.parity_stripes})")
    except FileExistsError as e:
        console.print(f"[red]{e}[/red]")


def do_add() -> None:
    vol = select_volume()
    if not vol:
        return
    files = console.input("  File paths (space-separated): ").strip()
    paths = files.split()
    if not paths:
        console.print("[red]No files specified.[/red]")
        return
    count = add_files(vol, paths)
    console.print(f"[green]Staged {count} file(s).[/green]")


def do_burn() -> None:
    vol = select_volume()
    if not vol:
        return
    passphrase = console.input("  Encryption passphrase (enter to skip): ").strip()
    discs = burn_volume(vol, passphrase=passphrase)
    if discs:
        console.print(f"[green]Burned {len(discs)} disc(s).[/green]")


def do_verify() -> None:
    vol = select_volume()
    if not vol:
        return
    verify_volume(vol)


def do_recover() -> None:
    vol = select_volume()
    if not vol:
        return
    output = console.input("  Output directory: ").strip()
    if not output:
        console.print("[red]Output directory required.[/red]")
        return
    passphrase = console.input("  Decryption passphrase: ").strip()
    success = recover_volume(vol, output, passphrase=passphrase)
    if success:
        console.print("[green]Recovery complete.[/green]")


def do_status() -> None:
    vol = select_volume()
    if not vol:
        return
    status_volume(vol)


def do_list() -> None:
    volumes = list_volumes()
    if not volumes:
        console.print("[dim]No volumes found.[/dim]")
        return
    for v in volumes:
        console.print(f"  - {v}")


def interactive_loop() -> None:
    print_banner()
    while True:
        console.print()
        print_menu()
        choice = console.input("\n  Choice: ").strip().lower()

        actions = {
            "n": do_init,
            "a": do_add,
            "b": do_burn,
            "v": do_verify,
            "r": do_recover,
            "s": do_status,
            "l": do_list,
        }

        if choice == "q":
            console.print("[dim]Bye![/dim]")
            break
        elif choice in actions:
            try:
                actions[choice]()
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")
        else:
            console.print("[yellow]Unknown command.[/yellow]")
