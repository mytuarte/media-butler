import logging

import discord

from config import Config
from models.notification import MovieNotification
from services.log_service import logger


class DiscordService:
    def __init__(self):
        logging.basicConfig(level=logging.DEBUG)

        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)

        @self.client.event
        async def on_ready():
            logger.info(f"Discord connected as {self.client.user}")

    async def start(self):
        logger.info(f"Discord token loaded: {Config.DISCORD_TOKEN is not None}")
        logger.info("Connecting to Discord...")

        await self.client.start(Config.DISCORD_TOKEN)

        logger.info("Discord client stopped.")

    async def send_movie_notification(
        self,
        movie: MovieNotification,
    ):
        channel = self.client.get_channel(Config.DISCORD_CHANNEL_ID)

        if channel is None:
            raise RuntimeError("Discord channel not found.")

        if isinstance(movie.requester, int):
            requester = f"<@{movie.requester}>"
        elif movie.requester:
            requester = movie.requester
        else:
            requester = "Unknown"

        embed = discord.Embed(
            title=f"🎬 {movie.title} ({movie.year})",
            description=f"**{movie.status}**",
            color=0x2ECC71,
        )

        embed.add_field(
            name="👤 Requested By",
            value=requester,
            inline=True,
        )

        embed.add_field(
            name="🎞 Quality",
            value=movie.quality,
            inline=True,
        )

        embed.set_footer(text="Media Butler")

        await channel.send(
            content=requester if isinstance(movie.requester, int) else None,
            embed=embed,
)

        logger.info(f"Discord notification sent for '{movie.title}'.")