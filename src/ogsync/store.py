"""Local persistence for tracking synced events, enabling idempotent sync runs."""

from pathlib import Path
from typing import TYPE_CHECKING, cast

from sqlite_utils import Database

from ogsync.core import PathInput, now_utc
from ogsync.logging_config import get_logger
from ogsync.settings import settings

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlite_utils.db import Table

    from ogsync.models import CalendarEvent

logger = get_logger(__name__)

TABLE_NAME = "synced_events"

_SCHEMA: dict[str, type] = {
    "id": str,
    "external_id": str,
    "source": str,
    "destination": str,
    "recurrence_id": str,
    "status": str,
    "title": str,
    "start_time": str,
    "end_time": str,
    "first_synced_at": str,
    "last_seen_at": str,
}


def open_db(path: PathInput | None = None) -> Database:
    """Open (creating if needed) the local sync-state database."""
    path = Path(path) if path is not None else settings.state_db_path
    db = Database(path)
    if TABLE_NAME not in db.table_names():
        table = cast("Table", db[TABLE_NAME])
        _ = table.create(_SCHEMA, pk="id", not_null={"external_id", "source", "destination"})
        _ = table.create_index(["source", "destination"])
        _ = table.create_index(["recurrence_id"])
        _ = table.create_index(["external_id"])
    return db


class SyncStore:
    """Wraps the synced_events table for a specific source/destination pair."""

    def __init__(self, source: str, destination: str, db: "Database | None" = None) -> None:
        self.source: str = source
        self.destination: str = destination
        self.db: Database = db if db is not None else open_db()

    @property
    def table(self) -> "Table":
        return cast("Table", self.db[TABLE_NAME])

    def known_ids(self) -> set[str]:
        """All local ids currently tracked for this source/destination pair."""
        rows = self.table.rows_where(  # pyright: ignore[reportUnknownMemberType]
            "source = ? and destination = ?", [self.source, self.destination]
        )
        return {row["id"] for row in rows}

    def external_id_for(self, event_id: str) -> "str | None":
        row = next(
            self.table.rows_where(  # pyright: ignore[reportUnknownMemberType]
                "id = ? and source = ? and destination = ?",
                [event_id, self.source, self.destination],
            ),
            None,
        )
        return row["external_id"] if row else None

    def record_synced(self, event: "CalendarEvent", external_id: str) -> None:
        """Upsert the mapping for a single synced event; idempotent by event.id."""
        assert event.id is not None, "Event must have an id before being recorded as synced."
        now = now_utc().isoformat()
        existing = next(self.table.rows_where("id = ?", [event.id]), None)  # pyright: ignore[reportUnknownMemberType]
        row = {
            "id": event.id,
            "external_id": external_id,
            "source": self.source,
            "destination": self.destination,
            "recurrence_id": event.recurrence_id,
            "status": event.status.value,
            "title": event.title,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat() if event.end_time else None,
            "first_synced_at": existing["first_synced_at"] if existing else now,
            "last_seen_at": now,
        }
        _ = self.table.upsert(row, pk="id")

    def record_all_synced(
        self, events_and_external_ids: "Iterable[tuple[CalendarEvent, str]]"
    ) -> None:
        for event, external_id in events_and_external_ids:
            self.record_synced(event, external_id)

    def forget(self, event_ids: "Iterable[str]") -> None:
        """Remove tracking rows, typically after deleting from the destination."""
        ids = list(event_ids)
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        _ = self.table.db.execute(  # pyright: ignore[reportUnknownMemberType]
            f"delete from {TABLE_NAME} where id in ({placeholders}) "
            + "and source = ? and destination = ?",
            [*ids, self.source, self.destination],
        )

    def stale_ids(self, current_ids: "set[str]") -> set[str]:
        """Ids previously synced but no longer present in the current source fetch."""
        return self.known_ids() - current_ids
