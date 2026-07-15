from enum import Enum


class MonitoringState(Enum):
    NOT_ADDED = "not_added"
    COMING_SOON = "coming_soon"
    DOWNLOADING = "downloading"
    AVAILABLE = "available"
