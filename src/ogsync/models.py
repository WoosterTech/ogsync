"""Created by ogsync.devtools.create_module."""

import datetime as dt
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Self
from zoneinfo import ZoneInfo

from attrmagic import ClassBase, SimpleListRoot
from pydantic import Field, field_validator, model_validator

from ogsync.core import now_utc
from ogsync.identity import generated_event_id
from ogsync.logging_config import get_logger
from ogsync.settings import settings

if TYPE_CHECKING:
    from pydantic.config import ExtraValues

logger = get_logger(__name__)


class EventStatus(StrEnum):
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"

    def __rich_repr__(self):
        yield self.value


class CalendarEvent(ClassBase):
    """Represents a calendar event with support for timezones, recurrence, and all-day events."""

    id: str | None = None
    title: str
    location: str | None = None
    start_time: dt.datetime
    end_time: dt.datetime | None = None
    all_day: bool = False
    timezone: str = ""
    recurrence_rule: str | None = None
    recurrence_id: str | None = None
    categories: list[str] = Field(default_factory=list)
    status: EventStatus = EventStatus.CONFIRMED

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def make_tz_aware(cls, v: Any) -> Any:  # pyright: ignore[reportExplicitAny, reportAny]
        """If naive, localize using the global default tz before anything else touches it."""
        if isinstance(v, dt.datetime) and v.tzinfo is None:
            v = v.replace(tzinfo=settings.zoneinfo)
        return v

    @field_validator("id", mode="before")
    @classmethod
    def validate_id(cls, v: Any) -> Any:  # pyright: ignore[reportExplicitAny, reportAny]
        if v is not None and not v:
            raise ValueError("ID must not be empty.")
        return v

    @model_validator(mode="after")
    def resolve_timezone(self) -> Self:
        """Capture the zone name BEFORE anything gets converted to UTC.

        Runs first among the 'after' validators, so every later step — including on a second pass
        from e.g., model_validate_json — can rely on self.timezone being populated and treat it as
        being populated and treat it as the source of truth for 'local'.
        """
        if not self.timezone:
            tzinfo = self.start_time.tzinfo
            self.timezone = str(tzinfo) if tzinfo else settings.default_time_zone
        return self

    def _local_date(self, dt_obj: dt.datetime) -> dt.date:
        """Calendar date in self.timezone, regardless of what zone dt_obj is in.

        Makes date derivation idempotent across repeated validations.

        Args:
            dt_obj (dt.datetime): The datetime object to convert to the local date.

        Returns:
            date: The calendar date in the local timezone.

        """
        return dt_obj.astimezone(ZoneInfo(self.timezone)).date()

    @model_validator(mode="after")
    def validate_start_before_end(self) -> Self:
        if not self.all_day and self.end_time is not None and self.end_time < self.start_time:
            raise ValueError("End time must be on or after the start time.")
        if self.all_day:
            # this allows for arbitrary times for input of all_day events
            if self.end_time is None:
                raise ValueError("End time must not be None for all-day events.")
            local_tz = ZoneInfo(self.timezone)
            local_start = self.start_time.astimezone(local_tz)
            local_end = self.end_time.astimezone(local_tz)
            if local_end.date() < local_start.date() or (
                local_end.date() == local_start.date()
                and local_end.time() == dt.datetime.min.time()
            ):
                raise ValueError("End date must be after the start date.")

        return self

    @model_validator(mode="after")
    def normalize_all_day_bounds(self) -> Self:
        """Must run BEFORE the UTC conversion below.

        Idempotent — Two things make repeated validation (e.g., a JSON round trip) stable instead of drifting:

          1. Dates are re-derived via `self.timezone`, not `start_time.tzinfo` (which is UTC after the first pass).
          2. The exclusive-end bump (+1 day) only applies when `end_time` IS NOT already sitting on local midnight.
             Without that check, a boundary already advanced by a prior pass gets treated as 'some time on the
             last included day' and gets bumped again — drifting forward by a day on every validation.

        'midnight' only means something in local time.

        Runs first because it's defined first.

        Runs after `validate_start_before_end` to guarantee that start DATE is not after end DATE.
        """
        if self.all_day:
            assert self.end_time is not None, "End time must not be None for all-day events."
            local_tz = ZoneInfo(self.timezone)
            local_start = self.start_time.astimezone(local_tz)
            local_end = self.end_time.astimezone(local_tz)

            start_date = local_start.date()

            if local_end.time() == dt.datetime.min.time():
                # already an exclusive midnight boundary
                end_date = local_end.date()
            else:
                # some time ON the last included day; bump past it
                end_date = local_end.date() + dt.timedelta(days=1)

            self.start_time = dt.datetime.combine(
                start_date, dt.datetime.min.time(), tzinfo=local_tz
            )
            self.end_time = dt.datetime.combine(end_date, dt.datetime.min.time(), tzinfo=local_tz)

        return self

    @model_validator(mode="after")
    def normalize_to_utc(self) -> Self:
        """Pull tz from start_time if it has one and none was explicitly set."""

        # Normalize both timestamps to UTC for storage/comparison
        self.start_time = self.start_time.astimezone(dt.UTC)
        self.end_time = self.end_time.astimezone(dt.UTC) if self.end_time is not None else None
        return self

    @model_validator(mode="after")
    def ensure_id(self) -> Self:
        """Ensure the event has an ID, generating one if necessary."""
        if self.id is None:
            self.id = generated_event_id(
                title=self.title,
                start_time=self.start_time,
                end_time=self.end_time,
                all_day=self.all_day,
                location=self.location,
                recurrence_rule=self.recurrence_rule,
                recurrence_id=self.recurrence_id,
            )
        return self

    def is_upcoming(self, now: dt.datetime | None = None) -> bool:
        """True if the event is upcoming or currently active.

        An event without an end time is treated as a point-in-time event and is
        upcoming only until its start time.

        If `now` is not provided, the current time in the default time zone is used.
        """
        now = now or now_utc()
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt.UTC)

        if self.end_time is None:
            return self.start_time >= now
        return self.end_time >= now


class CalendarEvents(SimpleListRoot[CalendarEvent]):
    def get_upcoming(self, now: dt.datetime | None = None) -> Self:
        """Get all upcoming events from the list.

        If `now` is not provided, the current time in the default time zone is used.

        Creates a new `CalendarEvents` instance containing only the upcoming events.
        """
        now = now or now_utc()
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt.UTC)

        upcoming_events = [event for event in self if event.is_upcoming(now)]
        return self.__class__(root=upcoming_events)

    def validate_and_add(
        self,
        obj: object,
        *,
        strict: bool | None = None,
        extra: "ExtraValues | None" = None,
        from_attributes: bool | None = None,
        context: Any | None = None,  # pyright: ignore[reportExplicitAny]
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> None:
        """Validate the object and add it to the list if valid."""
        if not isinstance(obj, CalendarEvent):
            obj = CalendarEvent.model_validate(
                obj,
                strict=strict,
                extra=extra,
                from_attributes=from_attributes,
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        self.append(obj)

    def sort(self) -> None:
        self[:] = sorted(self, key=lambda e: e.start_time)
