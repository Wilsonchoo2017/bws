"""BWS scrape CLI commands."""

import typer
from rich.console import Console
from rich.table import Table

from bws.db.connection import get_connection
from bws.db.schema import init_schema
from bws.services.bricklink.parser import is_valid_bricklink_url, parse_bricklink_url
from bws.services.bricklink.repository import (
    get_item,
    get_items_for_scraping,
    list_items,
    upsert_item,
)
from bws.services.bricklink.scraper import ScrapeResult, scrape_batch_sync, scrape_item_sync
from bws.services.brickranker.scraper import scrape_retirement_tracker_sync
from bws.services.worldbricks.scraper import scrape_set_sync
from bws.types.models import BricklinkData, WatchStatus


console = Console()
scrape_group = typer.Typer(help="Scrape Bricklink data", no_args_is_help=True)


def _print_scrape_result(result: ScrapeResult) -> None:
    """Print a scrape result to console."""
    if result.success:
        console.print(f"[green]Success:[/green] {result.item_id}")
        if result.data:
            console.print(f"  Title: {result.data.title or 'N/A'}")
            console.print(f"  Year: {result.data.year_released or 'N/A'}")
            if result.data.six_month_new:
                box = result.data.six_month_new
                console.print(
                    f"  6-mo New: {box.times_sold or 0} sales, avg ${(box.avg_price.amount / 100) if box.avg_price else 0:.2f}"
                )
    else:
        console.print(f"[red]Failed:[/red] {result.item_id} - {result.error}")


@scrape_group.command(name="item")
def scrape_item_cmd(
    url: str = typer.Argument(..., help="Bricklink URL to scrape"),
    no_save: bool = typer.Option(default=False, help="Don't save to database"),
) -> None:
    """Scrape a single Bricklink item."""
    if not is_valid_bricklink_url(url):
        console.print("[red]Error:[/red] Invalid Bricklink URL")
        console.print("Expected format: https://www.bricklink.com/catalogPG.asp?S=75192-1")
        raise typer.Exit(1)

    console.print(f"[blue]Scraping:[/blue] {url}")

    conn = get_connection()
    init_schema(conn)

    result = scrape_item_sync(conn, url, save=not no_save)
    _print_scrape_result(result)

    conn.close()

    if not result.success:
        raise typer.Exit(1)


@scrape_group.command(name="queue")
def scrape_queue_cmd(
    limit: int = typer.Option(10, "--limit", "-l", help="Maximum items to scrape"),
) -> None:
    """Process items due for scraping from the queue."""
    conn = get_connection()
    init_schema(conn)

    items = get_items_for_scraping(conn, limit=limit)

    if not items:
        console.print("[yellow]No items due for scraping[/yellow]")
        conn.close()
        return

    console.print(f"[blue]Found {len(items)} items to scrape[/blue]")

    def progress_callback(current: int, total: int, result: ScrapeResult) -> None:
        status = "[green]OK[/green]" if result.success else "[red]FAIL[/red]"
        console.print(f"[{current}/{total}] {result.item_id}: {status}")

    results = scrape_batch_sync(conn, items, progress_callback=progress_callback)

    # Summary
    success_count = sum(1 for r in results if r.success)
    console.print(f"\n[blue]Summary:[/blue] {success_count}/{len(results)} successful")

    conn.close()


@scrape_group.command(name="add")
def scrape_add_cmd(
    url: str = typer.Argument(..., help="Bricklink URL to add to watch list"),
) -> None:
    """Add an item to the watch list for scraping."""
    if not is_valid_bricklink_url(url):
        console.print("[red]Error:[/red] Invalid Bricklink URL")
        raise typer.Exit(1)

    try:
        item_type, item_id = parse_bricklink_url(url)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1) from e

    conn = get_connection()
    init_schema(conn)

    # Check if already exists
    existing = get_item(conn, item_id)
    if existing:
        console.print(f"[yellow]Item {item_id} already in watch list[/yellow]")
        conn.close()
        return

    # Add with minimal data (will be populated on first scrape)
    data = BricklinkData(
        item_id=item_id,
        item_type=item_type,
    )
    upsert_item(conn, data)

    console.print(f"[green]Added {item_id} to watch list[/green]")
    console.print("Run 'bws scrape queue' to scrape pending items")

    conn.close()


@scrape_group.command(name="list")
def scrape_list_cmd(
    status: str = typer.Option("active", "--status", "-s", help="Filter by watch status"),
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum items to show"),
) -> None:
    """List watched items."""
    try:
        watch_status = WatchStatus(status) if status else None
    except ValueError:
        console.print("[red]Error:[/red] Invalid status. Use: active, paused, stopped, archived")
        raise typer.Exit(1) from None

    conn = get_connection()
    init_schema(conn)

    items = list_items(conn, watch_status=watch_status, limit=limit)

    if not items:
        console.print("[yellow]No items found[/yellow]")
        conn.close()
        return

    table = Table(title=f"Watched Items ({len(items)})")
    table.add_column("Item ID", style="cyan")
    table.add_column("Type")
    table.add_column("Title")
    table.add_column("Year")
    table.add_column("Status")
    table.add_column("Last Scraped")

    for item in items:
        last_scraped = (
            item.last_scraped_at.strftime("%Y-%m-%d") if item.last_scraped_at else "Never"
        )
        table.add_row(
            item.item_id,
            item.item_type,
            (item.title or "")[:40],
            str(item.year_released or "-"),
            item.watch_status.value,
            last_scraped,
        )

    console.print(table)
    conn.close()


@scrape_group.command(name="worldbricks")
def scrape_worldbricks_cmd(
    set_number: str = typer.Argument(..., help="Set number to scrape (e.g., 75192)"),
) -> None:
    """Scrape WorldBricks for set metadata (release year, retirement year, parts count)."""

    console.print(f"[blue]Searching WorldBricks for:[/blue] {set_number}")

    conn = get_connection()
    init_schema(conn)

    result = scrape_set_sync(conn, set_number)

    if result is None:
        console.print(f"[yellow]No data found for set {set_number}[/yellow]")
        conn.close()
        raise typer.Exit(1)

    console.print(f"[green]Success:[/green] {result.set_number}")
    console.print(f"  Name: {result.set_name or 'N/A'}")
    console.print(f"  Year Released: {result.year_released or 'N/A'}")
    console.print(f"  Year Retired: {result.year_retired or 'N/A'}")
    console.print(f"  Parts Count: {result.parts_count or 'N/A'}")
    if result.dimensions:
        console.print(f"  Dimensions: {result.dimensions}")

    conn.close()


@scrape_group.command(name="brickranker")
def scrape_brickranker_cmd() -> None:
    """Scrape BrickRanker retirement tracker (full page scrape)."""

    console.print("[blue]Scraping BrickRanker retirement tracker...[/blue]")

    conn = get_connection()
    init_schema(conn)

    items = scrape_retirement_tracker_sync(conn)

    if not items:
        console.print("[yellow]No items found[/yellow]")
        conn.close()
        return

    # Count retiring soon items
    retiring_soon_count = sum(1 for item in items if item.retiring_soon)

    console.print(f"[green]Success:[/green] Scraped {len(items)} items")
    console.print(f"  Retiring Soon: {retiring_soon_count}")

    # Show first few retiring soon items
    retiring_items = [item for item in items if item.retiring_soon][:5]
    if retiring_items:
        console.print("\n[yellow]Sample Retiring Soon:[/yellow]")
        for item in retiring_items:
            console.print(f"  {item.set_number}: {item.set_name}")

    conn.close()
