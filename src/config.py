import os

from dotenv import load_dotenv

environment = os.getenv(
    "MEDIA_BUTLER_ENV",
    "dev",
).lower()

dotenv_file = "config/.env.dev" if environment == "dev" else "config/.env"

load_dotenv(dotenv_file)


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)

    return int(value) if value else None


def _float_config_value(
    name: str,
    default: str,
) -> float:
    return float(os.getenv(name, default))


def _positive_int_config_value(
    name: str,
    default: str,
) -> int:
    """Read an interval configuration value that must be a positive integer."""
    value = int(os.getenv(name, default))

    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")

    return value


class Config:
    ENVIRONMENT = environment

    # Discord
    # Discord
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
    DISCORD_PLEX_NOTIFICATIONS_CHANNEL_ID = int(
        os.getenv("DISCORD_PLEX_NOTIFICATIONS_CHANNEL_ID")
    )
    DISCORD_ADMIN_CHANNEL_ID = int(os.getenv("DISCORD_ADMIN_CHANNEL_ID"))
    DISCORD_MEDIA_SEARCH_CHANNEL_ID = int(os.getenv("DISCORD_MEDIA_SEARCH_CHANNEL_ID"))
    DISCORD_MEDIA_ATTENTION_CHANNEL_ID = int(
        os.getenv("DISCORD_MEDIA_ATTENTION_CHANNEL_ID")
    )
    DISCORD_TRENDING_MOVIES_CHANNEL_ID = _optional_int(
        "DISCORD_TRENDING_MOVIES_CHANNEL_ID"
    )
    DISCORD_TRENDING_TV_CHANNEL_ID = _optional_int("DISCORD_TRENDING_TV_CHANNEL_ID")
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
    MEDIA_ATTENTION_STALL_MINUTES = _positive_int_config_value("MEDIA_ATTENTION_STALL_MINUTES", "20")
    MEDIA_ATTENTION_TV_STALL_MINUTES = _positive_int_config_value("MEDIA_ATTENTION_TV_STALL_MINUTES", "120")
    MEDIA_ATTENTION_INTERVAL_SECONDS = _float_config_value(
        "MEDIA_ATTENTION_INTERVAL_SECONDS",
        "60",
    )
    HEALTH_MONITOR_INTERVAL_SECONDS = _positive_int_config_value(
        "HEALTH_MONITOR_INTERVAL_SECONDS",
        "60",
    )
    TRENDING_MOVIES_INTERVAL_HOURS = _float_config_value(
        "TRENDING_MOVIES_INTERVAL_HOURS",
        "24",
    )
    TRENDING_TV_INTERVAL_HOURS = _float_config_value(
        "TRENDING_TV_INTERVAL_HOURS",
        "24",
    )

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

    # qBittorrent
    QBITTORRENT_URL = os.getenv("QBITTORRENT_URL")
    QBITTORRENT_USERNAME = os.getenv("QBITTORRENT_USERNAME")
    QBITTORRENT_PASSWORD = os.getenv("QBITTORRENT_PASSWORD")

    # Plex
    PLEX_URL = os.getenv("PLEX_URL")
    PLEX_TOKEN = os.getenv("PLEX_TOKEN")
    PLEX_INVENTORY_CACHE_SECONDS = _float_config_value(
        "PLEX_INVENTORY_CACHE_SECONDS",
        "300",
    )

    # Filesystem
    MEDIA_ROOT = os.getenv("MEDIA_ROOT")
    STORAGE_WARNING_THRESHOLD_PERCENT = int(
        os.getenv(
            "STORAGE_WARNING_THRESHOLD_PERCENT",
            "15",
        )
    )
    STORAGE_CRITICAL_THRESHOLD_PERCENT = int(
        os.getenv(
            "STORAGE_CRITICAL_THRESHOLD_PERCENT",
            "5",
        )
    )

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

    @classmethod
    def qbittorrent_monitoring_enabled(cls) -> bool:
        """Return whether qBittorrent monitoring is configured completely."""
        settings = (
            cls.QBITTORRENT_URL,
            cls.QBITTORRENT_USERNAME,
            cls.QBITTORRENT_PASSWORD,
        )

        if not any(settings):
            return False

        if not all(settings):
            raise ValueError(
                "QBITTORRENT_URL, QBITTORRENT_USERNAME, and "
                "QBITTORRENT_PASSWORD must all be configured to enable "
                "qBittorrent monitoring."
            )

        return True
