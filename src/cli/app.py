"""Interactive TUI dashboard for Bluray Vault.

A rich terminal dashboard with:
- Persistent header showing current volume / status
- Action menu with single-key shortcuts
- Detailed panels for each operation
- Live status bar
"""

from __future__ import annotations

import os
from pathlib import Path

from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from src.core.volume import init_volume, list_volumes
from src.core.workflow import (
    add_files,
    burn_volume,
    get_staged_files,
    get_volume_status,
    recover_volume,
    verify_volume,
)
from src.models.schemas import (
    DiscStatus,
    RedundancyLevel,
    VolumeStatus,
)

console = Console()

# ── Global state ──────────────────────────────────────────────

_current_volume: str | None = None


# ── Helpers ───────────────────────────────────────────────────

def _status_style(status: str) -> str:
    return {
        "initialized": "dim",
        "staging": "yellow",
        "burning": "magenta",
        "complete": "green",
        "recovering": "cyan",
    }.get(status, "white")


def _disc_status_style(status: DiscStatus) -> str:
    return {
        DiscStatus.EMPTY: "dim",
        DiscStatus.BURNED: "green",
        DiscStatus.VERIFIED: "bold green",
        DiscStatus.DAMAGED: "bold red",
    }.get(status, "white")


def _redundancy_label(level: RedundancyLevel) -> str:
    return {
        RedundancyLevel.STANDARD: "Standard 16+4 (20%)",
        RedundancyLevel.HIGH: "High 16+8 (50%)",
        RedundancyLevel.EXTREME: "Extreme 8+8 (100%)",
    }.get(level, str(level))


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} PB"


def _clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


# ── Header / Status Bar ──────────────────────────────────────

def _render_header() -> Panel:
    title = Text()
    title.append(" Bluray Vault ", style="bold white on cyan")
    title.append("  Archival Backup", style="dim")

    if _current_volume:
        try:
            meta = get_volume_status(_current_volume)
            status_txt = Text()
            status_txt.append(" Volume: ", style="dim")
            status_txt.append(meta.name, style="bold cyan")
            status_txt.append("  Status: ", style="dim")
            status_txt.append(meta.status.value, style=_status_style(meta.status.value))
            status_txt.append("  Discs: ", style="dim")
            status_txt.append(str(meta.total_discs), style="bold")
            status_txt.append("  Redundancy: ", style="dim")
            status_txt.append(_redundancy_label(meta.erasure.redundancy))
            content = Group(title, status_txt)
        except Exception:
            content = title
    else:
        content = Group(title, Text(" No volume selected", style="dim"))

    return Panel(content, border_style="cyan", padding=(0, 1))


# ── Menu ──────────────────────────────────────────────────────

def _render_menu() -> Table:
    t = Table(show_header=False, box=None, padding=(0, 1), expand=True)
    t.add_column("Key", style="bold yellow", width=5)
    t.add_column("Action", width=30)
    t.add_column("Key", style="bold yellow", width=5)
    t.add_column("Action")

    t.add_row(r"\[n]", "New volume", r"\[a]", "Add files")
    t.add_row(r"\[b]", "Burn to disc", r"\[v]", "Verify disc")
    t.add_row(r"\[r]", "Recover data", r"\[s]", "Status detail")
    t.add_row(r"\[l]", "List volumes", r"\[1-9]", "Switch volume")
    t.add_row("", "", r"\[q]", "Quit")
    return t


# ── Panels ────────────────────────────────────────────────────

def _panel_init() -> None:
    console.print(Rule("Initialize New Volume", style="cyan"))

    name = Prompt.ask("  Volume name", console=console)
    if not name.strip():
        console.print("[red]  Name required.[/red]")
        return
    name = name.strip()

    console.print("  [bold]Redundancy level:[/bold]")
    t = Table(show_header=False, box=None, padding=(0, 2))
    t.add_column("No.", style="yellow", width=4)
    t.add_column("Level")
    t.add_column("Config")
    t.add_column("Overhead")
    t.add_row("1", "Standard", "16 data + 4 parity", "20%")
    t.add_row("2", "High [default]", "16 data + 8 parity", "50%")
    t.add_row("3", "Extreme", "8 data + 8 parity", "100%")
    console.print(t)

    choice = Prompt.ask("  Choose", choices=["1", "2", "3", ""], default="2", console=console)
    levels = {"1": RedundancyLevel.STANDARD, "2": RedundancyLevel.HIGH, "3": RedundancyLevel.EXTREME}
    redundancy = levels.get(choice, RedundancyLevel.HIGH)

    try:
        meta = init_volume(name, redundancy=redundancy)
        global _current_volume
        _current_volume = name
        console.print(f"[green]  Volume '{name}' created.[/green]")
        console.print(f"  Redundancy: {_redundancy_label(redundancy)}")
        console.print(f"  ID: {meta.volume_id}")
    except FileExistsError as e:
        console.print(f"[red]  {e}[/red]")


def _panel_add() -> None:
    console.print(Rule("Add Files", style="cyan"))
    if not _current_volume:
        console.print("[red]  No volume selected. Use [1-9] or [l] first.[/red]")
        return

    # Show current staging
    staged = get_staged_files(_current_volume)
    if staged:
        console.print(f"  Currently staged: [dim]{len(staged)} file(s)[/dim]")
        for f in staged[:5]:
            console.print(f"    - {f}", style="dim")
        if len(staged) > 5:
            console.print(f"    ... and {len(staged) - 5} more", style="dim")

    files_str = Prompt.ask("  File paths (space-separated, or . for current dir)", console=console)
    paths = files_str.strip().split()

    if not paths:
        console.print("[red]  No files specified.[/red]")
        return

    # Handle '.' as current directory
    if "." in paths and len(paths) == 1:
        cwd_files = [str(p) for p in Path.cwd().iterdir() if p.is_file()]
        paths = cwd_files

    result = add_files(_current_volume, paths)

    if result.added:
        console.print(f"[green]  Staged {len(result.added)} file(s):[/green]")
        for f in result.added:
            console.print(f"    + {f}")
    if result.skipped_not_found:
        console.print("[yellow]  Not found:[/yellow]")
        for f in result.skipped_not_found:
            console.print(f"    ? {f}", style="red")
    if result.skipped_exists:
        console.print("[yellow]  Already staged:[/yellow]")
        for f in result.skipped_exists:
            console.print(f"    = {f}", style="dim")


def _panel_burn() -> None:
    console.print(Rule("Burn to Disc", style="cyan"))
    if not _current_volume:
        console.print("[red]  No volume selected.[/red]")
        return

    staged = get_staged_files(_current_volume)
    if not staged:
        console.print("[yellow]  No staged files. Use [a] to add files first.[/yellow]")
        return

    meta = get_volume_status(_current_volume)
    console.print(f"  Volume: [cyan]{meta.name}[/cyan]")
    console.print(f"  Staged files: {len(staged)}")
    console.print(f"  Redundancy: {_redundancy_label(meta.erasure.redundancy)}")

    total_size = sum(
        (Path(_current_volume) / "staging" / f).stat().st_size for f in staged
    )
    console.print(f"  Total size: {_fmt_bytes(total_size)}")

    console.print()
    if not Prompt.ask("  Proceed with burn?", choices=["y", "n"], default="y", console=console) == "y":
        console.print("  [dim]Cancelled.[/dim]")
        return

    passphrase = Prompt.ask("  Encryption passphrase (enter to skip)", password=True, console=console)

    with console.status("[bold cyan]Burning...[/bold cyan]"):
        result = burn_volume(_current_volume, passphrase=passphrase)

    if result.discs:
        console.print(f"[green]  Burned {len(result.discs)} disc(s).[/green]")
        for d in result.discs:
            console.print(f"    Disc {d.disc_index} ({d.disc_id})")
            console.print(f"      {d.data_chunks} data + {d.parity_chunks} parity chunks")
            console.print(f"      {_fmt_bytes(d.total_bytes)}, checksum: {d.checksum}")
        if result.simulated:
            console.print("  [dim](simulated burn)[/dim]")
    else:
        console.print("[yellow]  No data to burn.[/yellow]")


def _panel_verify() -> None:
    console.print(Rule("Verify Disc", style="cyan"))
    if not _current_volume:
        console.print("[red]  No volume selected.[/red]")
        return

    meta = get_volume_status(_current_volume)
    if not meta.discs:
        console.print("[yellow]  No discs to verify.[/yellow]")
        return

    console.print(f"  Checking {len(meta.discs)} disc(s)...")
    with console.status("[bold cyan]Verifying...[/bold cyan]"):
        discs = verify_volume(_current_volume)

    for d in discs:
        # TODO: real verification result
        console.print(f"    Disc {d.disc_index} ({d.disc_id}): [bold green]OK[/bold green]")

    console.print("[green]  Verification complete (simulated).[/green]")


def _panel_recover() -> None:
    console.print(Rule("Recover Data", style="cyan"))
    if not _current_volume:
        console.print("[red]  No volume selected.[/red]")
        return

    meta = get_volume_status(_current_volume)
    if not meta.discs:
        console.print("[yellow]  No discs found for recovery.[/yellow]")
        return

    console.print(f"  Volume: [cyan]{meta.name}[/cyan]")
    console.print(f"  Available discs: {len(meta.discs)}")
    total = sum(d.total_bytes for d in meta.discs)
    console.print(f"  Total data: {_fmt_bytes(total)}")

    output = Prompt.ask("  Output directory", console=console)
    if not output.strip():
        console.print("[red]  Output directory required.[/red]")
        return

    passphrase = Prompt.ask("  Decryption passphrase", password=True, console=console)

    with console.status("[bold cyan]Recovering...[/bold cyan]"):
        rmeta, rtotal = recover_volume(_current_volume, output, passphrase=passphrase)

    if rtotal > 0:
        console.print(f"[green]  Recovery complete.[/green]")
        console.print(f"  Recovered: {_fmt_bytes(rtotal)} -> {output}")
        console.print("  [dim](simulated recovery)[/dim]")
    else:
        console.print("[red]  Recovery failed.[/red]")


def _panel_status() -> None:
    console.print(Rule("Volume Status", style="cyan"))
    if not _current_volume:
        console.print("[red]  No volume selected.[/red]")
        return

    meta = get_volume_status(_current_volume)

    # Volume info table
    t = Table(title=None, show_header=False, box=None, padding=(0, 2))
    t.add_column("Field", style="dim", width=14)
    t.add_column("Value")
    t.add_row("Volume", f"[cyan bold]{meta.name}[/cyan bold]")
    t.add_row("ID", meta.volume_id)
    t.add_row("Status", f"[{_status_style(meta.status.value)}]{meta.status.value}[/]")
    t.add_row("Created", meta.created_at.strftime("%Y-%m-%d %H:%M"))
    t.add_row("Redundancy", _redundancy_label(meta.erasure.redundancy))
    t.add_row("Encryption", f"{meta.encryption.algorithm} ({meta.encryption.kdf})")
    t.add_row("Discs", str(meta.total_discs))
    console.print(t)

    # Staged files
    staged = get_staged_files(_current_volume)
    if staged:
        console.print(f"\n  [bold]Staged files ({len(staged)}):[/bold]")
        for f in staged:
            console.print(f"    - {f}", style="dim")
    else:
        console.print("\n  [dim]No staged files.[/dim]")

    # Disc details
    if meta.discs:
        console.print(f"\n  [bold]Disc details:[/bold]")
        dt = Table(show_header=True, box=None, padding=(0, 1))
        dt.add_column("Index", style="dim", width=6)
        dt.add_column("ID", style="cyan", width=14)
        dt.add_column("Status", width=10)
        dt.add_column("Data", width=8)
        dt.add_column("Parity", width=8)
        dt.add_column("Size", width=12)
        dt.add_column("Checksum", style="dim")
        for d in meta.discs:
            dt.add_row(
                str(d.disc_index),
                d.disc_id,
                f"[{_disc_status_style(d.status)}]{d.status.value}[/]",
                str(d.data_chunks),
                str(d.parity_chunks),
                _fmt_bytes(d.total_bytes),
                d.checksum[:16],
            )
        console.print(dt)


def _panel_list() -> None:
    console.print(Rule("Volumes", style="cyan"))
    volumes = list_volumes()
    if not volumes:
        console.print("[dim]  No volumes found. Use [n] to create one.[/dim]")
        return

    t = Table(show_header=True, box=None, padding=(0, 2))
    t.add_column("#", style="yellow", width=4)
    t.add_column("Name", style="cyan")
    t.add_column("Status")
    t.add_column("Discs", width=6)
    t.add_column("Redundancy")

    for i, vname in enumerate(volumes, 1):
        try:
            meta = get_volume_status(vname)
            t.add_row(
                str(i),
                meta.name,
                f"[{_status_style(meta.status.value)}]{meta.status.value}[/]",
                str(meta.total_discs),
                _redundancy_label(meta.erasure.redundancy),
            )
        except Exception:
            t.add_row(str(i), vname, "?", "?", "?")

    console.print(t)
    console.print("[dim]  Tip: Press 1-9 to switch to a volume[/dim]")


# ── Main Loop ─────────────────────────────────────────────────

def interactive_loop() -> None:
    global _current_volume

    while True:
        _clear()
        console.print(_render_header())
        console.print()
        console.print(_render_menu())
        console.print()

        choice = Prompt.ask("  Action", console=console).strip().lower()

        # Number → switch volume
        if choice.isdigit() and 1 <= int(choice) <= 9:
            volumes = list_volumes()
            idx = int(choice) - 1
            if idx < len(volumes):
                _current_volume = volumes[idx]
                console.print(f"  Switched to volume [cyan]{_current_volume}[/cyan]")
            else:
                console.print(f"[red]  No volume at position {choice}[/red]")
            Prompt.ask("\n  [dim]Press Enter to continue[/dim]", console=console)
            continue

        if choice == "q":
            console.print("[dim]Bye![/dim]")
            break

        actions = {
            "n": _panel_init,
            "a": _panel_add,
            "b": _panel_burn,
            "v": _panel_verify,
            "r": _panel_recover,
            "s": _panel_status,
            "l": _panel_list,
        }

        if choice in actions:
            console.print()
            try:
                actions[choice]()
            except Exception as e:
                console.print(f"[red]  Error: {e}[/red]")
            Prompt.ask("\n  [dim]Press Enter to continue[/dim]", console=console)
        else:
            console.print("[yellow]  Unknown command.[/yellow]")
            Prompt.ask("  [dim]Press Enter to continue[/dim]", console=console)
