import os
from dotenv import load_dotenv

load_dotenv("config/.env")


class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

    OVERSEERR_URL = os.getenv("OVERSEERR_URL")
    OVERSEERR_API_KEY = os.getenv("OVERSEERR_API_KEY")

    USERS = {
        "Mike": int(os.getenv("MIKE_ID")),
        "Derek": int(os.getenv("DEREK_ID")),
        "Jay": int(os.getenv("JAY_ID")),
    }