"""Created by ogsync.devtools.create_module."""

import datetime as dt

import win32com.client

from ogsync.logging_config import get_logger

logger = get_logger(__name__)


def get_calendar() -> "win32com.client.CDispatch":
    logger.info("Fetching Outlook calendar...")
    logger.debug("Initializing Outlook application...")
    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")  # pyright: ignore[reportAny]

    logger.debug("Fetching default Calendar folder...")
    return outlook.GetDefaultFolder(  # pyright: ignore[reportAny]
        9
    )  # 9 corresponds to the Calendar folder in Outlook


def get_appointments(days_ahead: int = 90) -> "win32com.client.CDispatch":
    calendar = get_calendar()

    items = calendar.Items  # pyright: ignore[reportAny]

    items.IncludeRecurrences = (
        True  # must be set before restricting items to include recurring appointments
    )
    items.Sort(  # must happen AFTER IncludeRecurrences is set  # pyright: ignore[reportAny]
        "[Start]"
    )

    now = dt.datetime.now()
    end = now + dt.timedelta(days=days_ahead)

    fmt = "%m/%d/%Y %I:%M %p"  # restrict syntax requires 'mm/dd/yyyy hh:mm AM/PM'
    restriction = f"[Start] >= '{now.strftime(fmt)}' AND [Start] <= '{end.strftime(fmt)}'"

    return items.Restrict(restriction)  # pyright: ignore[reportAny]


def get_categorized_events(
    category: str, days_ahead: int = 90
) -> "list[win32com.client.CDispatch]":
    appointments = get_appointments(days_ahead)
    return [
        app
        for app in appointments  # pyright: ignore[reportUnknownVariableType]
        if app.Categories and category in [c.strip() for c in app.Categories.split(",")]  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    ]
