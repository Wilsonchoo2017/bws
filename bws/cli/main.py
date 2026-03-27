"""BWS CLI main entry point."""

import typer

from bws.cli.admin import admin_group
from bws.cli.analyze import analyze_group
from bws.cli.scrape import scrape_group
from bws.cli.value import value_group


app = typer.Typer(
    name="bws",
    help="BWS - Bricklink Warehouse System for LEGO market analysis",
    no_args_is_help=True,
)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """BWS - Bricklink Warehouse System for LEGO market analysis."""
    if ctx.obj is None:
        ctx.obj = {}


# Register subcommands
app.add_typer(scrape_group, name="scrape")
app.add_typer(analyze_group, name="analyze")
app.add_typer(admin_group, name="admin")
app.add_typer(value_group, name="value")


if __name__ == "__main__":
    app()
