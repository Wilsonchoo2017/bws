"""BWS value investing CLI commands."""

from datetime import UTC, datetime

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from bws.db.connection import get_connection
from bws.db.schema import init_schema
from bws.services.bricklink.repository import get_item, get_price_history, list_items
from bws.services.value_investing.types import ValueInputs
from bws.services.value_investing.value_calc import calculate_intrinsic_value
from bws.services.worldbricks.repository import get_set as get_worldbricks_set
from bws.types.models import WatchStatus


console = Console()
value_group = typer.Typer(help="Value investing analysis", no_args_is_help=True)


def _format_cents(cents: int) -> str:
    """Format cents as dollars."""
    return f"${cents / 100:.2f}"


def _format_multiplier(mult: float, explanation: str, applied: bool) -> str:
    """Format a multiplier for display."""
    status = "" if applied else " [dim](not applied)[/dim]"
    return f"{mult:.2f}  {explanation}{status}"


@value_group.command(name="item")
def value_item_cmd(
    item_id: str = typer.Argument(..., help="Item ID to analyze (e.g., 75192-1)"),
    margin: float = typer.Option(0.25, "--margin", "-m", help="Margin of safety override"),
    verbose: bool = typer.Option(default=False, help="Show detailed breakdown"),
) -> None:
    """Full value analysis for a single item."""
    conn = get_connection()
    init_schema(conn)

    # Get Bricklink item metadata
    bricklink_item = get_item(conn, item_id)
    if not bricklink_item:
        console.print(f"[red]Error:[/red] Item {item_id} not found in database")
        console.print("Run 'bws scrape item <url>' first to fetch data")
        conn.close()
        raise typer.Exit(1)

    # Get pricing data from price history
    price_history = get_price_history(conn, item_id, limit=1)
    if not price_history:
        console.print(f"[yellow]Warning:[/yellow] No price history for {item_id}")

    # Get WorldBricks data for additional metadata
    set_number = item_id.split("-")[0] if "-" in item_id else item_id
    worldbricks_data = get_worldbricks_set(conn, set_number)

    # Calculate years post retirement
    years_post_retirement = None
    if worldbricks_data and worldbricks_data.year_retired:
        current_year = datetime.now(tz=UTC).year
        years_post_retirement = current_year - worldbricks_data.year_retired

    # Extract pricing from price history
    bricklink_avg = None
    bricklink_max = None
    times_sold = None
    available_qty = None
    available_lots = None

    if price_history:
        latest = price_history[0]
        six_month_new = latest.get("six_month_new")
        current_new = latest.get("current_new")

        if six_month_new:
            if six_month_new.avg_price:
                bricklink_avg = six_month_new.avg_price.amount
            if six_month_new.max_price:
                bricklink_max = six_month_new.max_price.amount
            times_sold = six_month_new.times_sold
            available_qty = six_month_new.total_qty

        if current_new:
            available_lots = current_new.total_lots
            if available_qty is None:
                available_qty = current_new.total_qty

    # Calculate sales velocity (sales per day over 6 months)
    sales_velocity = None
    if times_sold is not None:
        sales_velocity = times_sold / 180  # 6 months = ~180 days

    # Get MSRP if available from worldbricks
    msrp = None
    if worldbricks_data and hasattr(worldbricks_data, "msrp"):
        msrp = getattr(worldbricks_data, "msrp", None)

    inputs = ValueInputs(
        msrp=msrp,
        bricklink_avg_price=bricklink_avg,
        bricklink_max_price=bricklink_max,
        sales_velocity=sales_velocity,
        times_sold=times_sold,
        available_qty=available_qty,
        available_lots=available_lots,
        parts_count=worldbricks_data.parts_count if worldbricks_data else None,
        years_post_retirement=years_post_retirement,
    )

    # Calculate value with margin override if provided
    breakdown = calculate_intrinsic_value(inputs)

    # Apply margin override if different from calculated
    recommended_buy = breakdown.recommended_buy_price
    effective_margin = breakdown.margin_of_safety
    if margin != 0.25:  # User provided custom margin
        recommended_buy = int(breakdown.intrinsic_value * (1 - margin))
        effective_margin = margin

    # Display results
    console.print()

    if breakdown.rejected:
        console.print(
            Panel(
                f"[red]REJECTED[/red]: {breakdown.rejection_reason}",
                title=f"Value Analysis: {item_id}",
                border_style="red",
            )
        )
        conn.close()
        return

    # Build output
    lines = []
    lines.append(
        f"[bold]Base Value:[/bold] {_format_cents(breakdown.base_value)} ({breakdown.base_value_source})"
    )
    lines.append("")

    if verbose:
        lines.append("[bold]Quality Multipliers:[/bold]")
        lines.append(
            f"  Retirement:    {_format_multiplier(breakdown.retirement_mult.multiplier, breakdown.retirement_mult.explanation, breakdown.retirement_mult.applied)}"
        )
        lines.append(
            f"  Theme:         {_format_multiplier(breakdown.theme_mult.multiplier, breakdown.theme_mult.explanation, breakdown.theme_mult.applied)}"
        )
        lines.append(
            f"  PPD:           {_format_multiplier(breakdown.ppd_mult.multiplier, breakdown.ppd_mult.explanation, breakdown.ppd_mult.applied)}"
        )
        lines.append(
            f"  Quality:       {_format_multiplier(breakdown.quality_mult.multiplier, breakdown.quality_mult.explanation, breakdown.quality_mult.applied)}"
        )
        lines.append(
            f"  Demand:        {_format_multiplier(breakdown.demand_mult.multiplier, breakdown.demand_mult.explanation, breakdown.demand_mult.applied)}"
        )
        lines.append(
            f"  Scarcity:      {_format_multiplier(breakdown.scarcity_mult.multiplier, breakdown.scarcity_mult.explanation, breakdown.scarcity_mult.applied)}"
        )
        lines.append("")
        lines.append("[bold]Risk Discounts:[/bold]")
        lines.append(
            f"  Liquidity:     {_format_multiplier(breakdown.liquidity_mult.multiplier, breakdown.liquidity_mult.explanation, breakdown.liquidity_mult.applied)}"
        )
        lines.append(
            f"  Volatility:    {_format_multiplier(breakdown.volatility_mult.multiplier, breakdown.volatility_mult.explanation, breakdown.volatility_mult.applied)}"
        )
        lines.append(
            f"  Saturation:    {_format_multiplier(breakdown.saturation_mult.multiplier, breakdown.saturation_mult.explanation, breakdown.saturation_mult.applied)}"
        )
        lines.append("")

    lines.append(f"[bold]Total Multiplier:[/bold] {breakdown.total_multiplier:.2f}x")
    lines.append("")
    lines.append(
        f"[bold green]Intrinsic Value:[/bold green]       {_format_cents(breakdown.intrinsic_value)}"
    )
    lines.append(
        f"[bold cyan]Recommended Buy Price:[/bold cyan] {_format_cents(recommended_buy)} ({int(effective_margin * 100)}% margin)"
    )

    # Compare to current price if available
    if bricklink_avg:
        lines.append("")
        lines.append(f"[bold]Current Avg Price:[/bold]     {_format_cents(bricklink_avg)}")
        if bricklink_avg < recommended_buy:
            upside = ((recommended_buy - bricklink_avg) / bricklink_avg) * 100
            lines.append(f"[bold green]Action: BUY[/bold green] ({upside:.0f}% below target)")
        elif bricklink_avg < breakdown.intrinsic_value:
            lines.append(
                "[bold yellow]Action: HOLD[/bold yellow] (below intrinsic, above buy price)"
            )
        else:
            lines.append("[bold red]Action: PASS[/bold red] (above intrinsic value)")

    title = f"Value Analysis: {item_id}"
    if bricklink_item.title:
        title = f"Value Analysis: {item_id} ({bricklink_item.title[:30]})"

    console.print(Panel("\n".join(lines), title=title, border_style="blue"))
    conn.close()


@value_group.command(name="opportunities")
def find_opportunities_cmd(
    min_margin: float = typer.Option(
        0.20, "--min-margin", "-m", help="Minimum margin below buy price"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum items to show"),
) -> None:
    """Find undervalued items with margin of safety."""
    conn = get_connection()
    init_schema(conn)

    # Get all active items
    items = list_items(conn, watch_status=WatchStatus.ACTIVE, limit=500)

    if not items:
        console.print("[yellow]No watched items found[/yellow]")
        conn.close()
        return

    console.print(f"[blue]Analyzing {len(items)} items...[/blue]")

    opportunities = []

    for item in items:
        # Get price history for this item
        price_history = get_price_history(conn, item.item_id, limit=1)
        if not price_history:
            continue

        latest = price_history[0]
        six_month_new = latest.get("six_month_new")
        current_new = latest.get("current_new")

        bricklink_avg = None
        times_sold = None
        available_qty = None
        available_lots = None

        if six_month_new:
            if six_month_new.avg_price:
                bricklink_avg = six_month_new.avg_price.amount
            times_sold = six_month_new.times_sold
            available_qty = six_month_new.total_qty

        if current_new:
            available_lots = current_new.total_lots

        if bricklink_avg is None:
            continue

        sales_velocity = times_sold / 180 if times_sold else None

        inputs = ValueInputs(
            bricklink_avg_price=bricklink_avg,
            sales_velocity=sales_velocity,
            times_sold=times_sold,
            available_qty=available_qty,
            available_lots=available_lots,
        )

        breakdown = calculate_intrinsic_value(inputs)

        if breakdown.rejected:
            continue

        # Check if current price is below recommended buy price
        if bricklink_avg < breakdown.recommended_buy_price:
            margin_pct = ((breakdown.recommended_buy_price - bricklink_avg) / bricklink_avg) * 100
            if margin_pct >= min_margin * 100:
                opportunities.append(
                    {
                        "item_id": item.item_id,
                        "title": item.title or "",
                        "current_price": bricklink_avg,
                        "intrinsic_value": breakdown.intrinsic_value,
                        "buy_price": breakdown.recommended_buy_price,
                        "margin_pct": margin_pct,
                    }
                )

    # Sort by margin percentage
    opportunities.sort(key=lambda x: x["margin_pct"], reverse=True)
    opportunities = opportunities[:limit]

    if not opportunities:
        console.print("[yellow]No opportunities found matching criteria[/yellow]")
        conn.close()
        return

    table = Table(title=f"Investment Opportunities ({len(opportunities)})")
    table.add_column("Item ID", style="cyan")
    table.add_column("Title")
    table.add_column("Current", justify="right")
    table.add_column("Intrinsic", justify="right")
    table.add_column("Buy Target", justify="right")
    table.add_column("Margin", justify="right", style="green")

    for opp in opportunities:
        table.add_row(
            opp["item_id"],
            opp["title"][:25],
            _format_cents(opp["current_price"]),
            _format_cents(opp["intrinsic_value"]),
            _format_cents(opp["buy_price"]),
            f"{opp['margin_pct']:.0f}%",
        )

    console.print(table)
    conn.close()


@value_group.command(name="refresh")
def refresh_valuations_cmd(
    limit: int = typer.Option(50, "--limit", "-l", help="Maximum items to refresh"),
) -> None:
    """Recalculate valuations for watched items."""
    conn = get_connection()
    init_schema(conn)

    items = list_items(conn, watch_status=WatchStatus.ACTIVE, limit=limit)

    if not items:
        console.print("[yellow]No watched items found[/yellow]")
        conn.close()
        return

    console.print(f"[blue]Refreshing valuations for {len(items)} items...[/blue]")

    success_count = 0
    rejected_count = 0

    for item in items:
        # Get price history for this item
        price_history = get_price_history(conn, item.item_id, limit=1)
        if not price_history:
            continue

        latest = price_history[0]
        six_month_new = latest.get("six_month_new")
        current_new = latest.get("current_new")

        bricklink_avg = None
        times_sold = None
        available_qty = None
        available_lots = None

        if six_month_new:
            if six_month_new.avg_price:
                bricklink_avg = six_month_new.avg_price.amount
            times_sold = six_month_new.times_sold
            available_qty = six_month_new.total_qty

        if current_new:
            available_lots = current_new.total_lots

        if bricklink_avg is None:
            continue

        sales_velocity = times_sold / 180 if times_sold else None

        inputs = ValueInputs(
            bricklink_avg_price=bricklink_avg,
            sales_velocity=sales_velocity,
            times_sold=times_sold,
            available_qty=available_qty,
            available_lots=available_lots,
        )

        breakdown = calculate_intrinsic_value(inputs)

        if breakdown.rejected:
            rejected_count += 1
        else:
            success_count += 1

    console.print(f"[green]Refreshed:[/green] {success_count} items")
    console.print(f"[yellow]Rejected:[/yellow] {rejected_count} items (failed hard gates)")
    conn.close()
