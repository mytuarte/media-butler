import asyncio
import threading
import traceback

from flask import Flask

from services.discord_service import DiscordService
from services.notification_service import NotificationService

app = Flask(__name__)

discord_service = DiscordService()
notification_service = NotificationService(discord_service)


def start_discord():
    print("Starting Discord thread...")
    try:
        asyncio.run(discord_service.start())
    except Exception:
        traceback.print_exc()


@app.get("/")
def home():
    return "Media Butler is running!"


@app.get("/test")
def test():
    future = asyncio.run_coroutine_threadsafe(
        notification_service.send_test_notification(),
        discord_service.client.loop,
    )

    future.result(timeout=10)

    return "Test notification sent!"


def main():
    discord_thread = threading.Thread(
        target=start_discord,
        daemon=True,
    )
    discord_thread.start()

    app.run(host="0.0.0.0", port=5000)


if __name__ == "__main__":
    main()