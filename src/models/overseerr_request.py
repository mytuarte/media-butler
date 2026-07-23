from dataclasses import dataclass


@dataclass
class OverseerrRequest:
    id: int

    status: int | None
    media_status: int | None

    requester: str | None
    requester_discord_id: int | None

    requested_date: str | None

    raw: dict
    media_id: int | None = None
