from dataclasses import dataclass, field

from models.discovery.discovery_selection import DiscoverySelection


@dataclass
class TrendingMoviesState:
    fingerprint: str
    message_id: int
    updated_at: str
    details_view_version: int = 0
    details_items: list[DiscoverySelection] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "TrendingMoviesState":
        fingerprint = data["fingerprint"]
        message_id = data["message_id"]
        updated_at = data["updated_at"]
        details_view_version = data.get("details_view_version", 0)
        details_items_data = data.get("details_items", [])

        if not isinstance(fingerprint, str):
            raise ValueError("Trending movies fingerprint must be a string.")

        if not isinstance(message_id, int) or isinstance(message_id, bool):
            raise ValueError("Trending movies message ID must be an integer.")

        if not isinstance(updated_at, str):
            raise ValueError("Trending movies update time must be a string.")

        if (
            not isinstance(details_view_version, int)
            or isinstance(details_view_version, bool)
            or details_view_version < 0
        ):
            raise ValueError(
                "Trending movies details view version must be non-negative."
            )

        if not isinstance(details_items_data, list):
            raise ValueError("Trending movies details items must be a list.")

        details_items = [
            DiscoverySelection.from_dict(item)
            for item in details_items_data
        ]

        return cls(
            fingerprint=fingerprint,
            message_id=message_id,
            updated_at=updated_at,
            details_view_version=details_view_version,
            details_items=details_items,
        )

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "message_id": self.message_id,
            "updated_at": self.updated_at,
            "details_view_version": self.details_view_version,
            "details_items": [item.to_dict() for item in self.details_items],
        }
