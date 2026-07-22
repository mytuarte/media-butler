import asyncio

from flask import Blueprint, request

from services.log_service import logger

webhook_routes = Blueprint(
    "webhook_routes",
    __name__,
)


def initialize(
    notification_service,
    discord_service,
    radarr_service,
    sonarr_service,
):
    @webhook_routes.post("/radarr")
    def radarr():
        logger.info("Received Radarr webhook.")

        payload = request.json

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

        payload = request.json

        series = payload.get("series", {})
        logger.info(
            f"Series: {series.get('title')} ({series.get('year')}) "
            f"TMDb: {series.get('tmdbId')}"
        )

        notification = sonarr_service.parse_notification(payload)

        logger.info(f"Requester resolved to: {notification.requester}")

        logger.info("Sending Discord notification...")

        future = asyncio.run_coroutine_threadsafe(
            notification_service.send_movie_notification(notification),
            discord_service.client.loop,
        )

        future.result(timeout=10)

        logger.info("Sonarr episode notification sent for %s", notification.title)

        return "", 200
