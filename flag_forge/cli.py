"""Flag Forge CLI - Feature flag management."""

from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .evaluator import evaluate_flag
from .flags import FlagStore
from .lifecycle import (
    generate_rollout_plan,
    get_lifecycle_stage,
    get_lifecycle_summary,
    suggest_action,
)
from .scanner import (
    find_stale_flags,
    find_undefined_flags,
    find_unused_flags,
    scan_codebase,
)

console = Console()


@click.group()
@click.version_option(__version__, prog_name="flag-forge")
@click.option("--file", "-f", "flags_file", default=".flags.yml", help="Path to flags YAML file.")
@click.pass_context
def cli(ctx: click.Context, flags_file: str) -> None:
    """Flag Forge - Git-centric feature flag system.

    Define, evaluate, and manage feature flags stored in version-controlled YAML.
    """
    ctx.ensure_object(dict)
    ctx.obj["flags_file"] = flags_file


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize a .flags.yml file with an example flag."""
    store = FlagStore(ctx.obj["flags_file"])
    if store.list_all():
        console.print(f"[yellow]{ctx.obj['flags_file']} already exists with {len(store.list_all())} flags.[/]")
        return

    store.create(
        name="example_feature",
        description="An example feature flag - delete this after testing",
        enabled=False,
        rollout=10,
        owner="your-team",
        targeting=[
            {"attribute": "plan", "operator": "in", "values": ["pro", "enterprise"]},
        ],
    )
    console.print(f"[green]Created {ctx.obj['flags_file']} with example flag.[/]")
    console.print("\nNext steps:")
    console.print("  flag-forge list           # View flags")
    console.print("  flag-forge create my_flag  # Create a flag")
    console.print("  flag-forge toggle my_flag  # Enable/disable")


@cli.command(name="list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def list_cmd(ctx: click.Context, as_json: bool) -> None:
    """List all feature flags."""
    store = FlagStore(ctx.obj["flags_file"])
    flags = store.list_all()

    if not flags:
        console.print("[yellow]No flags defined. Run 'flag-forge init' to get started.[/]")
        return

    if as_json:
        click.echo(json.dumps(flags, indent=2, default=str))
        return

    table = Table(title=f"Feature Flags ({len(flags)})")
    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("Enabled")
    table.add_column("Rollout", justify="right")
    table.add_column("Lifecycle", style="dim")
    table.add_column("Owner", style="dim")
    table.add_column("Description")

    for flag in flags:
        enabled = flag.get("enabled", False)
        enabled_str = "[green]ON[/]" if enabled else "[red]OFF[/]"
        rollout = flag.get("rollout", 100)
        stage = get_lifecycle_stage(flag)

        table.add_row(
            flag["name"],
            enabled_str,
            f"{rollout}%",
            stage,
            flag.get("owner", ""),
            (flag.get("description", ""))[:40],
        )

    console.print(table)


@cli.command()
@click.argument("name")
@click.option("--desc", "-d", default="", help="Description.")
@click.option("--enabled/--disabled", default=False, help="Initial state.")
@click.option("--rollout", "-r", default=100, type=int, help="Rollout percentage.")
@click.option("--owner", "-o", default="", help="Owner team/person.")
@click.option("--env", "-e", multiple=True, help="Allowed environments.")
@click.pass_context
def create(ctx: click.Context, name: str, desc: str, enabled: bool,
           rollout: int, owner: str, env: tuple[str, ...]) -> None:
    """Create a new feature flag."""
    store = FlagStore(ctx.obj["flags_file"])
    try:
        environments = list(env) if env else None
        flag = store.create(
            name=name,
            description=desc,
            enabled=enabled,
            rollout=rollout,
            owner=owner,
            environments=environments,
        )
        state = "[green]ON[/]" if enabled else "[red]OFF[/]"
        console.print(f"[green]Created flag:[/] {name} ({state}, {rollout}% rollout)")
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("name")
@click.pass_context
def toggle(ctx: click.Context, name: str) -> None:
    """Toggle a flag's enabled/disabled state."""
    store = FlagStore(ctx.obj["flags_file"])
    try:
        new_state = store.toggle(name)
        state_str = "[green]ON[/]" if new_state else "[red]OFF[/]"
        console.print(f"Flag '{name}' is now {state_str}")
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        sys.exit(1)


@cli.command()
@click.argument("name")
@click.option("--context", "-c", multiple=True, help="Context key=value pairs (e.g. user_id=123).")
@click.option("--env", "-e", default=None, help="Environment to evaluate for.")
@click.pass_context
def eval(ctx: click.Context, name: str, context: tuple[str, ...], env: str | None) -> None:
    """Evaluate a flag for a given context."""
    store = FlagStore(ctx.obj["flags_file"])
    flag_data = store.get_raw()

    if name not in flag_data:
        console.print(f"[red]Flag '{name}' not found.[/]")
        sys.exit(1)

    # Parse context
    eval_context: dict = {}
    for item in context:
        if "=" in item:
            key, value = item.split("=", 1)
            # Try to parse as int/float
            try:
                value = int(value)  # type: ignore
            except ValueError:
                try:
                    value = float(value)  # type: ignore
                except ValueError:
                    pass
            eval_context[key] = value

    result = evaluate_flag(name, flag_data[name], context=eval_context, environment=env)

    color = "green" if result.enabled else "red"
    console.print(f"\nFlag: [cyan]{name}[/]")
    console.print(f"Result: [{color}]{'ENABLED' if result.enabled else 'DISABLED'}[/]")
    console.print(f"Reason: {result.reason}")
    if eval_context:
        console.print(f"Context: {eval_context}")
    if env:
        console.print(f"Environment: {env}")
    console.print()


@cli.command()
@click.option("--dir", "-d", "scan_dir", default=".", help="Directory to scan.")
@click.option("--days", default=30, type=int, help="Days before a flag is considered stale.")
@click.pass_context
def stale(ctx: click.Context, scan_dir: str, days: int) -> None:
    """Find stale, unused, and undefined flags."""
    store = FlagStore(ctx.obj["flags_file"])
    flags = store.list_all()

    if not flags:
        console.print("[yellow]No flags defined.[/]")
        return

    console.print(f"[bold]Scanning {scan_dir} for flag usage...[/]\n")

    # Scan codebase
    code_refs = scan_codebase(scan_dir)

    # Find stale flags
    stale_flags = find_stale_flags(flags, stale_days=days)
    if stale_flags:
        console.print(f"[bold yellow]Stale Flags ({len(stale_flags)}):[/]")
        for f in stale_flags:
            console.print(f"  [yellow]{f['name']}[/]: {f['stale_reason']}")
        console.print()

    # Find unused flags
    unused = find_unused_flags(flags, code_refs)
    if unused:
        console.print(f"[bold red]Unused Flags ({len(unused)}):[/]")
        for f in unused:
            console.print(f"  [red]{f['name']}[/] - defined but not found in code")
        console.print()

    # Find undefined flags
    undefined = find_undefined_flags(flags, code_refs)
    if undefined:
        console.print(f"[bold magenta]Undefined Flags ({len(undefined)}):[/]")
        for name in undefined:
            refs = code_refs.get(name, [])
            locations = ", ".join(f"{r['file']}:{r['line']}" for r in refs[:3])
            console.print(f"  [magenta]{name}[/] - used in code but not defined ({locations})")
        console.print()

    if not stale_flags and not unused and not undefined:
        console.print("[green]All flags are healthy![/]")

    # Lifecycle summary
    summary = get_lifecycle_summary(flags)
    console.print("[bold]Lifecycle Summary:[/]")
    for stage, names in summary.items():
        if names:
            console.print(f"  {stage}: {', '.join(names)}")


@cli.command()
@click.option("--dir", "-d", "scan_dir", default=".", help="Directory to scan.")
@click.option("--remove", is_flag=True, help="Actually remove unused flags from .flags.yml.")
@click.pass_context
def cleanup(ctx: click.Context, scan_dir: str, remove: bool) -> None:
    """Clean up stale and unused flags."""
    store = FlagStore(ctx.obj["flags_file"])
    flags = store.list_all()
    code_refs = scan_codebase(scan_dir)
    unused = find_unused_flags(flags, code_refs)
    stale_on = [f for f in find_stale_flags(flags) if f.get("enabled")]

    candidates = []
    for f in unused:
        candidates.append({"name": f["name"], "reason": "unused in code"})
    for f in stale_on:
        if f["name"] not in [c["name"] for c in candidates]:
            candidates.append({"name": f["name"], "reason": "stale (always on)"})

    if not candidates:
        console.print("[green]No flags to clean up.[/]")
        return

    console.print(f"[bold]Cleanup candidates ({len(candidates)}):[/]")
    for c in candidates:
        console.print(f"  {c['name']}: {c['reason']}")

    if remove:
        for c in candidates:
            store.delete(c["name"])
            console.print(f"  [red]Removed {c['name']}[/]")
        console.print(f"\n[green]Removed {len(candidates)} flags.[/]")
    else:
        console.print("\nRun with --remove to delete these flags.")


if __name__ == "__main__":
    cli()
