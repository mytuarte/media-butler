import os

from dotenv import load_dotenv

environment = os.getenv(
    "MEDIA_BUTLER_ENV",
    "dev",
).lower()

dotenv_file = "config/.env.dev" if environment == "dev" else "config/.env"

load_dotenv(dotenv_file)


class Config:
    ENVIRONMENT = environment

    # Discord
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
    DISCORD_ADMIN_CHANNEL_ID = int(os.getenv("DISCORD_ADMIN_CHANNEL_ID"))
    DISCORD_MEDIA_SEARCH_CHANNEL_ID = int(os.getenv("DISCORD_MEDIA_SEARCH_CHANNEL_ID"))

    DELETE_SEARCH_MESSAGES = (
        os.getenv(
            "DELETE_SEARCH_MESSAGES",
            "true",
        ).lower()
        == "true"
    )

    DELETE_SEARCH_RESULTS = (
        os.getenv(
            "DELETE_SEARCH_RESULTS",
            "true",
        ).lower()
        == "true"
    )

    SEARCH_RESULT_LIFETIME_SECONDS = int(
        os.getenv(
            "SEARCH_RESULT_LIFETIME_SECONDS",
            "180",
        )
    )

    # TMDb
    TMDB_API_KEY = os.getenv("TMDB_API_KEY")

    # Radarr
    RADARR_URL = os.getenv("RADARR_URL")
    RADARR_API_KEY = os.getenv("RADARR_API_KEY")

    # Sonarr
    SONARR_URL = os.getenv("SONARR_URL")
    SONARR_API_KEY = os.getenv("SONARR_API_KEY")

    # Overseerr
    OVERSEERR_URL = os.getenv("OVERSEERR_URL")
    OVERSEERR_API_KEY = os.getenv("OVERSEERR_API_KEY")

    # SABnzbd
    SABNZBD_URL = os.getenv("SABNZBD_URL")
    SABNZBD_API_KEY = os.getenv("SABNZBD_API_KEY")

    # Filesystem
    MEDIA_ROOT = os.getenv("MEDIA_ROOT")

    # Discord Users
    USERS = {
        os.getenv("OVERSEERR_MIKE"): {
            "name": "Mike",
            "discord_id": int(os.getenv("MIKE_ID")),
        },
        os.getenv("OVERSEERR_DEREK"): {
            "name": "Derek",
            "discord_id": int(os.getenv("DEREK_ID")),
        },
        os.getenv("OVERSEERR_JAY"): {
            "name": "Jay",
            "discord_id": int(os.getenv("JAY_ID")),
        },
    }
