"""BWS admin CLI commands."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from bws.config.settings import BWS_DB_PATH
from bws.db.connection import get_connection
from bws.db.schema import drop_all_tables, get_table_stats, init_schema


console = Console()
admin_group = typer.Typer(help="Database administration commands", no_args_is_help=True)


@admin_group.command(name="init")
def admin_init_cmd() -> None:
    """Initialize the BWS database schema."""
    console.print(f"[blue]Database path:[/blue] {BWS_DB_PATH}")

    conn = get_connection()
    init_schema(conn)
    conn.close()

    console.print("[green]Database initialized successfully![/green]")


@admin_group.command(name="stats")
def admin_stats_cmd() -> None:
    """Show database statistics."""
    console.print(f"[blue]Database path:[/blue] {BWS_DB_PATH}")

    if not BWS_DB_PATH.exists():
        console.print("[yellow]Database does not exist yet[/yellow]")
        console.print("Run 'bws admin init' to create it")
        return

    conn = get_connection()
    stats = get_table_stats(conn)
    conn.close()

    table = Table(title="Database Statistics")
    table.add_column("Table", style="cyan")
    table.add_column("Rows", justify="right")

    for table_name, row_count in stats.items():
        table.add_row(table_name, str(row_count))

    console.print(table)


@admin_group.command(name="reset")
def admin_reset_cmd(
    force: bool = typer.Option(default=False, help="Skip confirmation prompt"),
) -> None:
    """Reset the database (drops all tables)."""
    if not force:
        console.print("[bold red]WARNING: This will delete ALL data![/bold red]")
        confirm = typer.confirm("Are you sure you want to reset the database?")
        if not confirm:
            console.print("[dim]Aborted[/dim]")
            raise typer.Exit(0)

    conn = get_connection()
    drop_all_tables(conn)
    init_schema(conn)
    conn.close()

    console.print("[green]Database reset successfully![/green]")


@admin_group.command(name="export")
def admin_export_cmd(
    output: str = typer.Argument(..., help="Output file path (.parquet or .csv)"),
    table: str = typer.Option("bricklink_items", "--table", "-t", help="Table to export"),
) -> None:
    """Export data to parquet or CSV format."""

    output_path = Path(output)

    if output_path.suffix not in (".parquet", ".csv"):
        console.print("[red]Error:[/red] Output file must be .parquet or .csv")
        raise typer.Exit(1)

    valid_tables = [
        "bricklink_items",
        "bricklink_price_history",
        "bricklink_monthly_sales",
        "product_analysis",
    ]

    if table not in valid_tables:
        console.print(f"[red]Error:[/red] Invalid table. Choose from: {', '.join(valid_tables)}")
        raise typer.Exit(1)

    conn = get_connection()

    try:
        if output_path.suffix == ".parquet":
            conn.execute(f"COPY {table} TO '{output_path}' (FORMAT PARQUET)")
        else:
            conn.execute(f"COPY {table} TO '{output_path}' (FORMAT CSV, HEADER)")

        console.print(f"[green]Exported {table} to {output_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e
    finally:
        conn.close()


@admin_group.command(name="path")
def admin_path_cmd() -> None:
    """Show the database file path."""
    console.print(f"[blue]Database path:[/blue] {BWS_DB_PATH}")

    if BWS_DB_PATH.exists():
        size_mb = BWS_DB_PATH.stat().st_size / (1024 * 1024)
        console.print(f"[dim]File size:[/dim] {size_mb:.2f} MB")
    else:
        console.print("[yellow]Database does not exist yet[/yellow]")
