from typing import Annotated

import typer
from rich.table import Table

from .core import GlobalCLIOptions, ProjectContext
from .logging_config import get_console, verbosity_option
from .settings import settings

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


@cli.command()
def sync(
    ctx: ProjectContext,
    days_ahead: Annotated[
        int, typer.Option(help="How many days ahead to sync events for.")
    ] = settings.default_sync_window_days,
) -> None:
    """Sync events from the Outlook calendar to Google Calendar."""
    from .adapters.gcal import GCalSink
    from .adapters.outlook import OutlookSource
    from .store import SyncStore
    from .sync import sync as run_sync

    source = OutlookSource()
    sink = GCalSink(calendar_id=settings.google_calendar_id)
    store = SyncStore(source="outlook", destination="gcal")

    run_sync(source, sink, store, days_ahead=days_ahead, console=console, dry_run=ctx.obj.dry_run)


@cli.command()
def list_synced(_ctx: ProjectContext):
    """List all events that have been synced to the destination.

    Uses a private property on the event to detect true synced events.
    """
    from .adapters.gcal import GCalSink

    sink = GCalSink(calendar_id=settings.google_calendar_id)

    synced_ids = sink.list_synced_ids()

    table = Table(title="Synced Event IDs")
    table.add_column("Event ID", justify="left", style="cyan", no_wrap=True, max_width=24)

    for event_id in synced_ids:
        table.add_row(event_id)

    console.print(table)


if __name__ == "__main__":
    cli()
