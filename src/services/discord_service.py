import logging

import discord

from config import Config
from models.notification import MovieNotification
from services.command_service import CommandService
from services.log_service import logger
from services.registry import services


class DiscordService:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)

        intents = discord.Intents.default()
        intents.message_content = True

        self.client = discord.Client(
            intents=intents,
        )

        self.command_service = CommandService()

        @self.client.event
        async def on_ready():
            logger.info("=" * 50)
            logger.info("Media Butler")
            logger.info(f"Environment : {Config.ENVIRONMENT.upper()}")
            logger.info(f"Discord Bot : {self.client.user}")
            logger.info("=" * 50)

            if services.health_monitor:
                services.health_monitor.start()

                logger.info("Health monitor started.")

        @self.client.event
        async def on_message(message):
            # Ignore messages from bots (including ourselves)
            if message.author.bot:
                return

            # Only process messages in approved channels
            allowed_channels = {
                Config.DISCORD_CHANNEL_ID,
                Config.DISCORD_ADMIN_CHANNEL_ID,
                Config.DISCORD_MEDIA_SEARCH_CHANNEL_ID,
            }

            if message.channel.id not in allowed_channels:
                return

            await self.command_service.handle_message(message)

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
            content=(requester if isinstance(movie.requester, int) else None),
            embed=embed,
        )

        logger.info(f"Discord notification sent for '{movie.title}'.")

    async def send_health_alert(
        self,
        embed: discord.Embed,
    ) -> discord.Message:
        channel = self.client.get_channel(Config.DISCORD_MEDIA_ATTENTION_CHANNEL_ID)

        if channel is None:
            raise RuntimeError("Media attention channel not found.")

        message = await channel.send(
            embed=embed,
        )

        return message

    async def delete_health_alert(
        self,
        message_id: int,
    ):
        channel = self.client.get_channel(Config.DISCORD_MEDIA_ATTENTION_CHANNEL_ID)

        if channel is None:
            raise RuntimeError("Media attention channel not found.")

        try:
            message = await channel.fetch_message(message_id)

            await message.delete()

        except discord.NotFound:
            pass
