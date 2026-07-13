import asyncio

from flask import Blueprint, jsonify

debug_routes = Blueprint(
    "debug_routes",
    __name__,
)


def initialize(
    discord_service,
    notification_service,
    overseerr_service,
    sonarr_search_service,
):
    @debug_routes.get("/debug/sonarr")
    def debug_sonarr():
        sonarr_search_service.search("")
        return "Printed first Sonarr series to console."

    @debug_routes.get("/debug/overseerr/test")
    def overseerr_test():
        return jsonify(
            overseerr_service.test_connection()
        )

    @debug_routes.get("/debug/overseerr/requests")
    def overseerr_requests():
        return jsonify(
            overseerr_service.get_requests()
        )

    @debug_routes.get("/debug/overseerr/request/<int:tmdb_id>")
    def overseerr_request(tmdb_id):
        return jsonify(
            overseerr_service.get_request(tmdb_id)
        )

    @debug_routes.get("/debug/overseerr/request/<int:tmdb_id>/dump")
    def overseerr_request_dump(tmdb_id):
        request = overseerr_service.debug_request(tmdb_id)

        if request is None:
            return (
                jsonify(
                    {
                        "error": "Request not found",
                    }
                ),
                404,
            )

        return jsonify(
            {
                "message": "Request printed to console.",
            }
        )

    @debug_routes.get("/debug/test")
    def test():
        future = asyncio.run_coroutine_threadsafe(
            notification_service.send_test_notification(),
            discord_service.client.loop,
        )

        future.result(timeout=10)

        return "Test notification sent!"