import os
from dotenv import load_dotenv

load_dotenv("config/.env")


class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

    OVERSEERR_URL = os.getenv("OVERSEERR_URL")
    OVERSEERR_API_KEY = os.getenv("OVERSEERR_API_KEY")

    USERS = {
        os.getenv("OVERSEERR_MIKE"): int(os.getenv("MIKE_ID")),
        os.getenv("OVERSEERR_DEREK"): int(os.getenv("DEREK_ID")),
        os.getenv("OVERSEERR_JAY"): int(os.getenv("JAY_ID")),
    }