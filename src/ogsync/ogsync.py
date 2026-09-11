from typing import Annotated

import typer

from .core import GlobalCLIOptions, ProjectContext
from .logging_config import get_console, verbosity_option

cli = typer.Typer(help="Main CLI for ogsync.")
console = get_console()


@cli.callback()
def main(
    ctx: ProjectContext,
    verbosity: Annotated[int, verbosity_option()] = 0,
    dry_run: Annotated[
        bool, typer.Option("-d", "--dry-run", help="Simulate actions without making changes.")
    ] = False,
) -> None:
    """Main entry point for the CLI, setting up global options and context."""
    ctx.obj = GlobalCLIOptions(verbosity=verbosity, dry_run=dry_run)


if __name__ == "__main__":
    cli()
