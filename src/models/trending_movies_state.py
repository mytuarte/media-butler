from dataclasses import dataclass


@dataclass
class TrendingMoviesState:
    fingerprint: str
    message_id: int
    updated_at: str

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "TrendingMoviesState":
        fingerprint = data["fingerprint"]
        message_id = data["message_id"]
        updated_at = data["updated_at"]

        if not isinstance(fingerprint, str):
            raise ValueError("Trending movies fingerprint must be a string.")

        if not isinstance(message_id, int) or isinstance(message_id, bool):
            raise ValueError("Trending movies message ID must be an integer.")

        if not isinstance(updated_at, str):
            raise ValueError("Trending movies update time must be a string.")

        return cls(
            fingerprint=fingerprint,
            message_id=message_id,
            updated_at=updated_at,
        )

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "message_id": self.message_id,
            "updated_at": self.updated_at,
        }
