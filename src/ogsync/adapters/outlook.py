"""Created by ogsync.devtools.create_module."""

import datetime as dt
from enum import Flag, IntEnum
from typing import TYPE_CHECKING, cast, override

from ogsync.adapters.base import CalendarSource
from ogsync.connections.outlook import get_categorized_events
from ogsync.logging_config import get_logger
from ogsync.models import CalendarEvents, EventStatus
from ogsync.settings import settings

if TYPE_CHECKING:
    import win32com.client

logger = get_logger(__name__)


class RecurrenceType(IntEnum):
    DAILY = 0
    WEEKLY = 1
    MONTHLY = 2
    MONTHLY_BYDAY = 3
    YEARLY = 5
    YEARLY_BYDAY = 6

    @property
    def map_frequency(self) -> str:
        mapping = {
            RecurrenceType.DAILY: "DAILY",
            RecurrenceType.WEEKLY: "WEEKLY",
            RecurrenceType.MONTHLY: "MONTHLY",
            RecurrenceType.MONTHLY_BYDAY: "MONTHLY",
            RecurrenceType.YEARLY: "YEARLY",
            RecurrenceType.YEARLY_BYDAY: "YEARLY",
        }
        return mapping.get(self, "UNKNOWN")


class ResponseStatus(IntEnum):
    # https://learn.microsoft.com/en-us/office/vba/api/outlook.olresponsestatus
    NONE = 0
    ORGANIZED = 1
    TENTATIVE = 2
    ACCEPTED = 3
    DECLINED = 4
    NOT_RESPONDED = 5


class MeetingStatus(IntEnum):
    # https://learn.microsoft.com/en-us/office/vba/api/outlook.olmeetingstatus
    NON_MEETING = 0  # useful for holidays
    MEETING = 1
    RECEIVED = 3
    CANCELED = 5
    RECEIVED_AND_CANCELED = 7


CANCELLED_MEETING = {MeetingStatus.CANCELED, MeetingStatus.RECEIVED_AND_CANCELED}
TENTATIVE_RESPONSE = {ResponseStatus.TENTATIVE, ResponseStatus.NOT_RESPONDED}


def resolve_status(
    appointment: "win32com.client.CDispatch",
) -> EventStatus:
    response_status = ResponseStatus(appointment.ResponseStatus)  # pyright: ignore[reportAny]
    meeting_status = MeetingStatus(appointment.MeetingStatus)  # pyright: ignore[reportAny]

    if meeting_status in CANCELLED_MEETING:
        return EventStatus.CANCELLED
    if response_status in TENTATIVE_RESPONSE:
        return EventStatus.TENTATIVE
    return EventStatus.CONFIRMED


class DayBits(Flag):
    SU = 1
    MO = 2
    TU = 4
    WE = 8
    TH = 16
    FR = 32
    SA = 64


def mask_to_byday(mask: int) -> list[str]:
    return [cast("str", day.name) for day in DayBits if day.value & mask]


# TODO: not used by OutlookSource, left for potential future use
def build_rrule(pattern: "win32com.client.CDispatch") -> str:
    """Build an RRULE string from a recurrence pattern."""
    parts: list[str] = []

    recurrence_type = RecurrenceType(pattern.RecurrenceType)  # pyright: ignore[reportAny]

    parts.append(f"FREQ={recurrence_type.map_frequency}")

    if pattern.Interval > 1:  # pyright: ignore[reportAny]
        parts.append(f"INTERVAL={pattern.Interval}")  # pyright: ignore[reportAny]

    match recurrence_type:
        case RecurrenceType.WEEKLY:
            days = mask_to_byday(pattern.DayOfWeekMask)  # pyright: ignore[reportAny]
            if days:
                parts.append(f"BYDAY={','.join(days)}")
        case _:
            # TODO: Handle other recurrence types like MONTHLY, YEARLY, etc.
            pass

    if not pattern.NoEndDate:  # pyright: ignore[reportAny]
        if pattern.Occurrences:  # pyright: ignore[reportAny]
            parts.append(f"COUNT={pattern.Occurrences}")  # pyright: ignore[reportAny]
        else:
            until = pattern.PatternEndDate.strftime("%Y%m%dT235959Z")  # pyright: ignore[reportAny]
            parts.append(f"UNTIL={until}")

    return ";".join(parts)


class OutlookSource(CalendarSource):
    def __init__(self, category: str = settings.default_sync_category) -> None:
        self.category: str = category

    @staticmethod
    def _as_utc_datetime(value: dt.datetime) -> dt.datetime:
        """Handle pywintypes.datetime objects and convert them to UTC datetime."""
        # assumes the input datetime is in UTC
        return dt.datetime(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            tzinfo=dt.UTC,
        )

    @classmethod
    def _appointment_to_data(cls, appointment: "win32com.client.CDispatch") -> dict[str, object]:
        data: dict[str, object] = {
            "id": appointment.EntryID,  # pyright: ignore[reportAny]
            "title": appointment.Subject,  # pyright: ignore[reportAny]
            "start_time": cls._as_utc_datetime(appointment.StartUTC),  # pyright: ignore[reportAny]
            "end_time": cls._as_utc_datetime(appointment.EndUTC),  # pyright: ignore[reportAny]
            "all_day": appointment.AllDayEvent,  # pyright: ignore[reportAny]
            "location": appointment.Location,  # pyright: ignore[reportAny]
            "timezone": settings.default_time_zone,
            "recurrence_id": appointment.GlobalAppointmentID,  # pyright: ignore[reportAny]
            "categories": appointment.Categories.split(",") if appointment.Categories else [],  # pyright: ignore[reportAny]
            "status": resolve_status(appointment),
        }
        return data

    @classmethod
    def _items_to_data(cls, items: list["win32com.client.CDispatch"]) -> list[dict[str, object]]:
        return [cls._appointment_to_data(item) for item in items]

    @override
    def get_events(self, days_ahead: int = 90) -> CalendarEvents:
        events = get_categorized_events(self.category, days_ahead=days_ahead)
        logger.debug(f"First event dir: {dir(events[0]) if events else 'No events'}")
        return CalendarEvents.model_validate(self._items_to_data(events))


if __name__ == "__main__":
    from rich import print as rprint

    outlook_source = OutlookSource()
    events = outlook_source.get_events()

    rprint(events[0])
