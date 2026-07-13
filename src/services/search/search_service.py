from abc import ABC, abstractmethod

from models.media_result import MediaResult


class SearchService(ABC):
    @abstractmethod
    def search(self, query: str) -> list[MediaResult]:
        """Search for media matching the query."""
        pass