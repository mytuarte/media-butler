from dataclasses import dataclass


@dataclass
class DownloadStatus:
    """
    Represents a media item's current download state.
    """

    name: str

    state: str

    progress: int

    eta: str
