"""Google Calendar authentication and API access."""

from typing import TypedDict, cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build  # pyright: ignore[reportUnknownVariableType]

from ogsync.logging_config import get_logger
from ogsync.settings import settings

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarInfo(TypedDict):
    id: str
    summary: str


def get_credentials() -> Credentials:
    """Get credentials for accessing the Google Calendar API.

    Uses the token and client secret files specified in the settings to obtain valid credentials.
    """
    credentials: Credentials | None = None

    if settings.google_token_path.exists():
        credentials = Credentials.from_authorized_user_file(  # pyright: ignore[reportUnknownMemberType]
            settings.google_token_path,
            SCOPES,
        )

    if credentials and credentials.expired and credentials.refresh_token:  # pyright: ignore[reportUnknownMemberType]
        credentials.refresh(Request())  # pyright: ignore[reportUnknownMemberType]
    elif not credentials or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            settings.google_client_secret_path,
            SCOPES,
        )
        credentials = cast("Credentials", flow.run_local_server(port=0))  # pyright: ignore[reportUnknownMemberType]
    _ = settings.google_token_path.write_text(credentials.to_json(), encoding="utf-8")  # pyright: ignore[reportUnknownMemberType]
    return credentials


def get_calendars() -> list[CalendarInfo]:
    with build("calendar", "v3", credentials=get_credentials()) as service:
        calendars: list[CalendarInfo] = []
        request = service.calendarList().list()

        while request is not None:
            response = request.execute()
            for calendar in response.get("items", []):
                calendar_id = calendar.get("id")
                if calendar_id is not None:
                    calendars.append(
                        {
                            "id": calendar_id,
                            "summary": calendar.get("summary", "(unnamed)"),
                        }
                    )
            request = service.calendarList().list_next(request, response)

    return calendars


def get_calendar_by_id(calendar_id: str = settings.google_calendar_id) -> CalendarInfo | None:
    for calendar in get_calendars():
        if calendar["id"] == calendar_id:
            return calendar
    return None


def main() -> None:
    for calendar in get_calendars():
        print(f"{calendar['summary']}: {calendar['id']}")


if __name__ == "__main__":
    main()
