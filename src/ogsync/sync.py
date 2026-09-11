"""Orchestrates moving events from a `CalendarSource` to a `CalendarSink`, tracked via `SyncStore`."""

from typing import TYPE_CHECKING

from rich.pretty import pretty_repr

from ogsync.core import hash_id
from ogsync.logging_config import get_logger

if TYPE_CHECKING:
    from rich.console import Console

    from ogsync.adapters.base import CalendarSink, CalendarSource
    from ogsync.store import SyncStore

logger = get_logger(__name__)


def console_print(console: "Console | None", message: str) -> None:
    if console is not None:
        console.print(message)


def sync(
    source: "CalendarSource",
    sink: "CalendarSink",
    store: "SyncStore",
    days_ahead: int = 90,
    *,
    console: "Console | None" = None,
    dry_run: bool = False,
) -> None:
    """Fetch events from `source`, upsert them into `sink`, and remove ones no longer present.

    For each fetched event: it is upserted into the sink (create or update), and the
    id mapping is recorded in `store`. Any previously synced event id that is no longer
    returned by the source (`store.stale_ids`) is deleted from the sink and forgotten.
    """
    events = source.get_events(days_ahead=days_ahead)
    console_print(console, f"Fetched {len(events)} events from source.")

    logger.debug(f"Current events fetched:\n{pretty_repr(events)}")
    current_ids = {event.id for event in events if event.id is not None}

    logger.debug(f"Current event IDs: {[hash_id(event_id) for event_id in current_ids]}")

    for event in events:
        assert event.id is not None, "CalendarEvent.id is always populated after validation."
        if dry_run:
            logger.info(f"[dry-run] would upsert {event.id} ({event.title!r})")
            continue
        external_id = sink.upsert_event(event)
        store.record_synced(event, external_id)
        logger.info(f"Synced {event.title!r} -> {external_id}")
        console_print(
            console, f"Synced {event.title!r}@{event.start_time.isoformat()} -> {external_id}"
        )

    for stale_id in store.stale_ids(current_ids):
        external_id = store.external_id_for(stale_id)
        if external_id is None:
            continue
        if dry_run:
            logger.info(f"[dry-run] would delete stale event {stale_id} ({external_id})")
            console_print(console, f"[dry-run] would delete stale event {stale_id} ({external_id})")
            continue
        sink.delete_event(external_id)
        store.forget([stale_id])
        logger.info(f"Removed stale event {hash_id(stale_id)} ({external_id})")
        console_print(console, f"Removed stale event {hash_id(stale_id)} ({external_id})")
