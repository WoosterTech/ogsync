"""Created by ogsync.devtools.create_module."""

import uuid
from typing import TYPE_CHECKING

from ogsync.logging_config import get_logger

if TYPE_CHECKING:
    from datetime import datetime

logger = get_logger(__name__)

# `uv run python -c "import uuid; print(uuid.uuid4())"`
OGSYNC_NAMESPACE = uuid.UUID("69629e44-ec08-4cec-93b5-0a3d81040ff9")


def generated_event_id(
    *,
    title: str,
    start_time: "datetime",
    end_time: "datetime | None",
    all_day: bool,
    location: str | None,
    recurrence_rule: str | None,
    recurrence_id: str | None,
) -> str:
    identity = "\x1f".join(
        [
            title.strip(),
            start_time.isoformat(),
            end_time.isoformat() if end_time is not None else "",
            str(all_day),
            location or "",
            recurrence_rule or "",
            recurrence_id or "",
        ]
    )

    return str(uuid.uuid5(OGSYNC_NAMESPACE, identity))
