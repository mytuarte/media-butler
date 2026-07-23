from config import Config
from models.overseerr_request import OverseerrRequest


class OverseerrRequestFactory:
    @staticmethod
    def from_api(request: dict) -> OverseerrRequest:
        media = request.get("media", {})

        display_name = (
            request.get("requestedBy", {})
            .get("displayName")
        )

        user = Config.USERS.get(display_name)

        if user:
            requester = user["name"]
            discord_id = user["discord_id"]
        else:
            requester = display_name
            discord_id = None

        return OverseerrRequest(
            id=request["id"],
            status=request.get("status"),
            media_status=media.get("status"),
            requester=requester,
            requester_discord_id=discord_id,
            requested_date=request.get("createdAt"),
            raw=request,
            media_id=media.get("id"),
        )
