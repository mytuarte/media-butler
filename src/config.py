import os
from dotenv import load_dotenv

load_dotenv("config/.env")


class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

    USERS = {
        "Mike": 297214021784829953,
        "Derek": 651223148385009683,
        "Jay": 598968345819086850,
    }