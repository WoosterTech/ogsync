"""Project level core functionality that doesn't fit into a more specific module."""

from dataclasses import dataclass
from datetime import UTC, datetime
from os import PathLike

from typer import Context

from .logging_config import get_logger, set_log_level

logger = get_logger(__name__)

# A type alias for inputs that can be either a string or a PathLike object representing a filesystem path. This is used for type annotations in functions that accept file paths, allowing for flexibility in the types of path inputs while maintaining type safety.
type PathInput = PathLike[str] | str


@dataclass
class GlobalCLIOptions:
    verbosity: int
    dry_run: bool = False

    def __post_init__(self) -> None:
        set_log_level(self.verbosity)


class ProjectContext(Context):
    """Custom Typer Context that adds the proper typing for `obj`."""

    obj: GlobalCLIOptions


def now_utc() -> datetime:
    """Get the timezone-aware current UTC datetime."""
    return datetime.now(UTC)


def truncate_id(event_id: str | None, length: int = 8) -> str:
    """Truncate an event ID to the specified length for easier display."""
    return event_id[:length] if event_id is not None else ""


def hash_id(event_id: str) -> str:
    """Generate a short hash of the event ID for easier display or comparison."""
    import hashlib

    return hashlib.sha256(event_id.encode()).hexdigest()[:8]
