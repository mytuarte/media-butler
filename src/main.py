import asyncio
import json
import threading
import traceback

from services.log_service import logger
from flask import Flask, jsonify, request

from services.discord_service import DiscordService
from services.notification_service import NotificationService
from services.radarr_service import RadarrService
from services.overseerr_service import OverseerrService

app = Flask(__name__)

discord_service = DiscordService()
notification_service = NotificationService(discord_service)
radarr_service = RadarrService()
overseerr_service = OverseerrService()


def start_discord():
    print("Starting Discord thread...")
    try:
        asyncio.run(discord_service.start())
    except Exception:
        traceback.print_exc()


@app.get("/")
def home():
    return "Media Butler is running!"


@app.get("/health")
def health():
    return jsonify(
        {
            "status": "healthy",
            "discord_connected": discord_service.client.is_ready(),
            "version": "0.1.0",
        }
    )


@app.get("/overseerr-test")
@app.get("/overseerr-requests")
def overseerr_requests():
    return jsonify(overseerr_service.get_requests())


def overseerr_test():
    return jsonify(overseerr_service.test_connection())


@app.get("/test")
def test():
    future = asyncio.run_coroutine_threadsafe(
        notification_service.send_test_notification(),
        discord_service.client.loop,
    )

    future.result(timeout=10)

    return "Test notification sent!"


@app.post("/radarr")
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

    logger.info("Discord notification sent successfully.")

    return "", 200


@app.post("/sonarr")
def sonarr():
    logger.info("Received Sonarr webhook.")

    payload = request.json

    logger.info("Sonarr payload:")
    logger.info(json.dumps(payload, indent=2))

    return "", 200


def main():
    discord_thread = threading.Thread(
        target=start_discord,
        daemon=True,
    )
    discord_thread.start()

    app.run(
        host="0.0.0.0",
        port=5000,
    )


if __name__ == "__main__":
    main()