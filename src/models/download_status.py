from dataclasses import dataclass


@dataclass
class DownloadStatus:
    """
    Represents a media item's current download state.
    """

    state: str
    progress: int
    eta: str