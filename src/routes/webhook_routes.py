import asyncio

from flask import Blueprint, request

from services.log_service import logger

webhook_routes = Blueprint(
    "webhook_routes",
    __name__,
)


def should_suppress_movie_notification(payload, suppression_store):
    """Atomically consume an exactly matching completed Radarr download."""
    return suppression_store is not None and suppression_store.consume_matching_import(payload)


def initialize(
    notification_service,
    discord_service,
    radarr_service,
    sonarr_service,
    series_completion_notification_service=None,
    downgrade_suppression_store=None,
):
    @webhook_routes.post("/radarr")
    def radarr():
        logger.info("Received Radarr webhook.")

        payload = request.json

        if payload.get("eventType") == "Test":
            logger.info("Received Radarr test webhook.")
            return "", 200

        if should_suppress_movie_notification(payload, downgrade_suppression_store):
            logger.info(
                "Suppressing requester completion notification for active "
                "downgrade of Radarr movie %s",
                payload.get("movie", {}).get("id"),
            )
            return "", 200

        movie = payload.get("movie", {})
        logger.info(
            f"Movie: {movie.get('title')} ({movie.get('year')}) "
            f"TMDb: {movie.get('tmdbId')}"
        )

        notification = radarr_service.parse_notification(payload)

        logger.info(f"Requester resolved to: {notification.requester}")

        logger.info("Sending Discord notification...")

        future = asyncio.run_coroutine_threadsafe(
            notification_service.send_movie_notification(notification),
            discord_service.client.loop,
        )

        future.result(timeout=10)

        logger.info("Radarr movie notification sent for %s", notification.title)

        return "", 200

    @webhook_routes.post("/sonarr")
    def sonarr():
        logger.info("Received Sonarr webhook.")
        payload = request.get_json(silent=True) or {}
        if series_completion_notification_service is None:
            logger.warning("Ignoring Sonarr webhook: series completion service is unavailable.")
            return "", 200
        future = asyncio.run_coroutine_threadsafe(
            series_completion_notification_service.process(payload),
            discord_service.client.loop,
        )
        future.result(timeout=35)
        return "", 200
