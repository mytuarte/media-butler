import asyncio
import threading
import traceback

from flask import Flask

from routes.debug_routes import (
    debug_routes,
    initialize as initialize_debug_routes,
)
from routes.system_routes import system_routes
from routes.webhook_routes import (
    initialize as initialize_webhook_routes,
    webhook_routes,
)
from services.discord_service import DiscordService
from services.notification_service import NotificationService
from services.overseerr_service import OverseerrService
from services.radarr_service import RadarrService
from services.search.sonarr_search_service import SonarrSearchService
from services.sonarr_service import SonarrService

app = Flask(__name__)

app.register_blueprint(system_routes)

discord_service = DiscordService()
notification_service = NotificationService(discord_service)
radarr_service = RadarrService()
sonarr_service = SonarrService()
sonarr_search_service = SonarrSearchService()
overseerr_service = OverseerrService()

initialize_webhook_routes(
    notification_service,
    discord_service,
    radarr_service,
    sonarr_service,
)

initialize_debug_routes(
    discord_service,
    notification_service,
    overseerr_service,
    sonarr_search_service,
)

app.register_blueprint(webhook_routes)
app.register_blueprint(debug_routes)


def start_discord():
    print("Starting Discord thread...")
    try:
        asyncio.run(discord_service.start())
    except Exception:
        traceback.print_exc()


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