from dataclasses import dataclass


@dataclass
class DeleteResult:
    media_title: str

    radarr_deleted: bool = False
    sonarr_deleted: bool = False
    files_deleted: bool = False
    overseerr_deleted: bool = False
    plex_watchlist_deleted: bool = False