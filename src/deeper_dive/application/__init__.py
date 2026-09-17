"""Application use-case boundary shared by CLI and TUI clients."""

from deeper_dive.application.events import ProgressEvent, ProgressSink
from deeper_dive.application.service import DeeperDiveService

__all__ = ["DeeperDiveService", "ProgressEvent", "ProgressSink"]
