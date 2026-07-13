import os

from dotenv import load_dotenv

load_dotenv("config/.env")


class Config:
    # Discord
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
    DISCORD_ADMIN_CHANNEL_ID = int(os.getenv("DISCORD_ADMIN_CHANNEL_ID"))

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