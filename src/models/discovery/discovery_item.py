from dataclasses import dataclass

from models.monitoring_state import MonitoringState


@dataclass
class DiscoveryItem:
    title: str
    media_type: str
    tmdb_id: int

    release_date: str | None = None
    poster_url: str | None = None
    overview: str | None = None

    monitoring_state: MonitoringState = MonitoringState.NOT_ADDED

    status_detail: str | None = None

    requester: str | None = None
