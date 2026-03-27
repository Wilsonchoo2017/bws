"""BWS analyze CLI commands."""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bws.db.connection import get_connection
from bws.db.schema import init_schema
from bws.services.analysis.availability import analyze_availability
from bws.services.analysis.demand import analyze_demand
from bws.services.analysis.recommendation import generate_recommendation
from bws.services.bricklink.repository import (
    get_item,
    get_monthly_sales,
    get_price_history,
    list_items,
)
from bws.types.models import Action, Urgency, WatchStatus


console = Console()
analyze_group = typer.Typer(help="Analyze Bricklink items", no_args_is_help=True)


def _action_color(action: Action) -> str:
    """Get color for action."""
    colors = {
        Action.STRONG_BUY: "bold green",
        Action.BUY: "green",
        Action.HOLD: "yellow",
        Action.SKIP: "red",
    }
    return colors.get(action, "white")


def _urgency_color(urgency: Urgency) -> str:
    """Get color for urgency."""
    colors = {
        Urgency.URGENT: "bold red",
        Urgency.MODERATE: "yellow",
        Urgency.LOW: "cyan",
        Urgency.NO_RUSH: "dim",
    }
    return colors.get(urgency, "white")


@analyze_group.command(name="item")
def analyze_item_cmd(
    item_id: str = typer.Argument(..., help="Bricklink item ID (e.g., 75192-1)"),
) -> None:
    """Analyze a single item and show recommendation."""
    conn = get_connection()
    init_schema(conn)

    # Get item
    item = get_item(conn, item_id)
    if not item:
        console.print(f"[red]Error:[/red] Item {item_id} not found in database")
        console.print("Add it first with: bws scrape add <url>")
        conn.close()
        raise typer.Exit(1)

    # Get price history
    history = get_price_history(conn, item_id, limit=1)
    current_new = history[0]["current_new"] if history else None
    six_month_new = history[0]["six_month_new"] if history else None

    # Get monthly sales
    monthly_sales = get_monthly_sales(conn, item_id)

    conn.close()

    # Run analysis
    demand_score = analyze_demand(monthly_sales, current_new)
    availability_score = analyze_availability(item, current_new, six_month_new)
    recommendation = generate_recommendation(item_id, demand_score, availability_score)

    # Display results
    console.print()
    console.print(Panel(f"[bold]{item.title or item_id}[/bold]", title="Analysis"))

    # Item info
    info_table = Table(show_header=False, box=None)
    info_table.add_column("Label", style="dim")
    info_table.add_column("Value")
    info_table.add_row("Item ID", item_id)
    info_table.add_row("Type", item.item_type)
    info_table.add_row("Year", str(item.year_released or "Unknown"))
    console.print(info_table)
    console.print()

    # Recommendation
    action_style = _action_color(recommendation.action)
    urgency_style = _urgency_color(recommendation.urgency)

    console.print(
        f"[bold]Recommendation:[/bold] [{action_style}]{recommendation.action.value.upper()}[/{action_style}]"
    )
    console.print(
        f"[bold]Urgency:[/bold] [{urgency_style}]{recommendation.urgency.value}[/{urgency_style}]"
    )
    console.print(
        f"[bold]Score:[/bold] {recommendation.overall.value}/100 (confidence: {recommendation.overall.confidence:.0%})"
    )
    console.print()

    # Scores breakdown
    if demand_score:
        console.print(f"[dim]Demand Score:[/dim] {demand_score.value}/100")
        console.print(f"  {demand_score.reasoning}")
    if availability_score:
        console.print(f"[dim]Availability Score:[/dim] {availability_score.value}/100")
        console.print(f"  {availability_score.reasoning}")
    console.print()

    # Risks and opportunities
    if recommendation.risks:
        console.print("[bold red]Risks:[/bold red]")
        for risk in recommendation.risks:
            console.print(f"  - {risk}")

    if recommendation.opportunities:
        console.print("[bold green]Opportunities:[/bold green]")
        for opp in recommendation.opportunities:
            console.print(f"  - {opp}")


@analyze_group.command(name="opportunities")
def analyze_opportunities_cmd(
    min_score: int = typer.Option(60, "--min-score", "-m", help="Minimum score threshold"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum items to show"),
) -> None:
    """Find investment opportunities from watched items."""
    conn = get_connection()
    init_schema(conn)

    items = list_items(conn, watch_status=WatchStatus.ACTIVE, limit=100)

    if not items:
        console.print("[yellow]No items in watch list[/yellow]")
        conn.close()
        return

    console.print(f"[blue]Analyzing {len(items)} items...[/blue]")

    opportunities = []

    for item in items:
        # Get data
        history = get_price_history(conn, item.item_id, limit=1)
        current_new = history[0]["current_new"] if history else None
        six_month_new = history[0]["six_month_new"] if history else None
        monthly_sales = get_monthly_sales(conn, item.item_id)

        # Analyze
        demand_score = analyze_demand(monthly_sales, current_new)
        availability_score = analyze_availability(item, current_new, six_month_new)
        recommendation = generate_recommendation(item.item_id, demand_score, availability_score)

        if recommendation.overall.value >= min_score:
            opportunities.append((item, recommendation))

    conn.close()

    # Sort by score descending
    opportunities.sort(key=lambda x: x[1].overall.value, reverse=True)
    opportunities = opportunities[:limit]

    if not opportunities:
        console.print(f"[yellow]No items found with score >= {min_score}[/yellow]")
        return

    # Display table
    table = Table(title=f"Investment Opportunities (score >= {min_score})")
    table.add_column("Item ID", style="cyan")
    table.add_column("Title")
    table.add_column("Score", justify="right")
    table.add_column("Action")
    table.add_column("Urgency")

    for item, rec in opportunities:
        action_style = _action_color(rec.action)
        urgency_style = _urgency_color(rec.urgency)

        table.add_row(
            item.item_id,
            (item.title or "")[:30],
            str(rec.overall.value),
            f"[{action_style}]{rec.action.value}[/{action_style}]",
            f"[{urgency_style}]{rec.urgency.value}[/{urgency_style}]",
        )

    console.print(table)


@analyze_group.command(name="refresh")
def analyze_refresh_cmd() -> None:
    """Refresh analysis for all watched items."""
    conn = get_connection()
    init_schema(conn)

    items = list_items(conn, watch_status=WatchStatus.ACTIVE, limit=1000)

    if not items:
        console.print("[yellow]No items to analyze[/yellow]")
        conn.close()
        return

    console.print(f"[blue]Refreshing analysis for {len(items)} items...[/blue]")

    counts = {
        Action.STRONG_BUY: 0,
        Action.BUY: 0,
        Action.HOLD: 0,
        Action.SKIP: 0,
    }

    for item in items:
        history = get_price_history(conn, item.item_id, limit=1)
        current_new = history[0]["current_new"] if history else None
        six_month_new = history[0]["six_month_new"] if history else None
        monthly_sales = get_monthly_sales(conn, item.item_id)

        demand_score = analyze_demand(monthly_sales, current_new)
        availability_score = analyze_availability(item, current_new, six_month_new)
        recommendation = generate_recommendation(item.item_id, demand_score, availability_score)

        counts[recommendation.action] += 1

    conn.close()

    # Summary
    console.print("\n[bold]Analysis Summary:[/bold]")
    console.print(f"  [bold green]Strong Buy:[/bold green] {counts[Action.STRONG_BUY]}")
    console.print(f"  [green]Buy:[/green] {counts[Action.BUY]}")
    console.print(f"  [yellow]Hold:[/yellow] {counts[Action.HOLD]}")
    console.print(f"  [red]Skip:[/red] {counts[Action.SKIP]}")
