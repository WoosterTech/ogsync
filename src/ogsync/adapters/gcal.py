"""Created by ogsync.devtools.create_module."""

from typing import TYPE_CHECKING, Any, Literal, cast, override

from googleapiclient.discovery import build  # pyright: ignore[reportUnknownVariableType]
from rich.pretty import pretty_repr

from ogsync.adapters.base import CalendarSink
from ogsync.connections.gcal import get_credentials
from ogsync.core import hash_id
from ogsync.logging_config import get_logger
from ogsync.models import EventStatus

if TYPE_CHECKING:
    from googleapiclient._apis.calendar.v3.resources import (  # pyright: ignore[reportMissingModuleSource]
        CalendarResource,
    )
    from googleapiclient._apis.calendar.v3.schemas import (  # pyright: ignore[reportMissingModuleSource]
        Event,
    )

    from ogsync.models import CalendarEvent


logger = get_logger(__name__)

# Private extended property used to tag events this tool owns, keyed by our own event.id,
# so an existing Google event can be found again without needing the local SyncStore.
EXTENDED_PROPERTY_KEY = "ogsync_id"


class GCalSink(CalendarSink):
    """Google Calendar sink implementation."""

    def __init__(
        self,
        calendar_id: str,
        service: Literal["calendar"] = "calendar",
        version: Literal["v3"] = "v3",
    ) -> None:
        self.calendar_id: str = calendar_id
        self.service: Literal["calendar"] = service
        self.version: Literal["v3"] = version

    @staticmethod
    def _build_body(event: "CalendarEvent") -> "Event":
        end_time = event.end_time or event.start_time
        if event.all_day:
            time_fields = {
                "start": {"date": event.start_time.date().isoformat()},
                "end": {"date": end_time.date().isoformat()},
            }
        else:
            time_fields = {
                "start": {"dateTime": event.start_time.isoformat()},
                "end": {"dateTime": end_time.isoformat()},
            }
        return {  # pyright: ignore[reportReturnType]
            "summary": event.title,
            "location": event.location or "",
            "status": "cancelled" if event.status is EventStatus.CANCELLED else "confirmed",
            "extendedProperties": {"private": {EXTENDED_PROPERTY_KEY: event.id}},
            **time_fields,
        }

    def _find_native_id(self, service: "CalendarResource", event_id: str) -> str | None:

        response = (
            service.events()
            .list(
                calendarId=self.calendar_id,
                privateExtendedProperty=f"{EXTENDED_PROPERTY_KEY}={event_id}",
                showDeleted=True,
            )
            .execute()
        )
        items = response.get("items", [])
        return items[0].get("id") if items else None

    @override
    def upsert_event(self, event: "CalendarEvent") -> str:
        """Create or update the Google Calendar event matching `event.id`.

        Looks up an existing event via the `ogsync_id` private extended property so repeated
        syncs of the same source event update in place instead of creating duplicates.
        """
        assert event.id is not None, "Event must have an id before being synced."
        logger.debug(f"Upserting event: {pretty_repr(event)}")
        body = self._build_body(event)
        with self._build() as service:
            native_id = self._find_native_id(service, event.id)

            if native_id is not None:
                logger.debug(f"Found native ID for event {hash_id(event.id)}: {native_id}")
                result = (
                    service.events()
                    .update(calendarId=self.calendar_id, eventId=native_id, body=body)
                    .execute()
                )
            else:
                logger.debug(
                    f"No native ID found for event {hash_id(event.id)}, creating a new one."
                )
                result = service.events().insert(calendarId=self.calendar_id, body=body).execute()

        result_id = result.get("id")
        logger.debug(f"Upserted event {hash_id(event.id)} with result ID: {result_id}")
        assert result_id is not None, "Failed to upsert event."
        return result_id

    @override
    def delete_event(self, event_id: str) -> None:
        """Delete a Google Calendar event by its native id."""
        with self._build() as service:
            service.events().delete(calendarId=self.calendar_id, eventId=event_id).execute()

    def _build(self) -> "CalendarResource":
        return build(self.service, self.version, credentials=get_credentials())

    @override
    def list_synced_ids(self) -> set[str]:
        """Native ids of Google Calendar events tagged with the `ogsync_id` extended property."""
        ids: set[str] = set()
        with self._build() as service:
            page_token: str | None = None
            while True:
                response = (
                    service.events()
                    .list(calendarId=self.calendar_id, pageToken=page_token)
                    .execute()
                )
                for item in cast("list[dict[str, Any]]", response.get("items", [])):  # pyright: ignore[reportExplicitAny]
                    private_props = item.get("extendedProperties", {}).get("private", {})  # pyright: ignore[reportAny]
                    logger.trace(
                        f"Private extended properties for item {item['id']}: {private_props}"
                    )
                    if EXTENDED_PROPERTY_KEY in private_props:
                        ids.add(item["id"])  # pyright: ignore[reportAny]
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
        return ids
