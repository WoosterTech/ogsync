"""Created by ogsync.devtools.create_module."""

import abc
from typing import TYPE_CHECKING

from ogsync.logging_config import get_logger

if TYPE_CHECKING:
    from ogsync.models import CalendarEvent, CalendarEvents

logger = get_logger(__name__)


class CalendarSource(abc.ABC):
    """Reads events from an origin system, normalied to `CalendarEvent`."""

    @abc.abstractmethod
    def get_events(self, days_ahead: int = 90) -> "CalendarEvents":
        """Fetches calendar events from the source system."""
        raise NotImplementedError


class CalendarSink(abc.ABC):
    """Writes CalendarEvents to a destination, tracking destination-native IDs."""

    @abc.abstractmethod
    def upsert_event(self, event: "CalendarEvent") -> str:
        """Create or update; returns the destinations native event id."""
        raise NotImplementedError

    @abc.abstractmethod
    def delete_event(self, event_id: str) -> None:
        """Deletes an event from the destination system by its native ID."""
        raise NotImplementedError

    @abc.abstractmethod
    def list_synced_ids(self) -> set[str]:
        """IDs in the destination that this tool manages."""
        raise NotImplementedError
