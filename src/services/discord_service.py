import logging

import discord

from config import Config
from models.health_issue import HealthIssue
from models.notification import MovieNotification
from services.command_service import CommandService
from services.log_service import logger
from services.registry import services
from views.health_alert_view import HealthAlertView
from views.media_attention_alert_view import MediaAttentionAlertView


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

            if services.media_attention_monitor and services.media_attention_monitor.start():
                logger.info("Media Attention monitor started.")

            if services.trending_movies:
                if services.trending_movies.start():
                    logger.info("Trending movies scheduler started.")

            if services.trending_tv:
                if services.trending_tv.start():
                    logger.info("Trending TV scheduler started.")

            if services.upcoming_movie_watchlist:
                if services.upcoming_movie_watchlist.start():
                    logger.info("Upcoming movie watchlist scheduler started.")

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

    async def send_embed(
        self,
        embed: discord.Embed,
    ):
        channel = self.client.get_channel(Config.DISCORD_CHANNEL_ID)

        if channel is None:
            raise RuntimeError("Discord channel not found.")

        await channel.send(embed=embed)

    async def send_health_alert(
        self,
        issue: HealthIssue,
    ) -> discord.Message:
        channel = self.client.get_channel(Config.DISCORD_MEDIA_ATTENTION_CHANNEL_ID)

        if channel is None:
            raise RuntimeError("Media attention channel not found.")

        message = await channel.send(
            embed=HealthAlertView.build(issue),
        )

        return message

    async def send_media_attention_alert(self, alert, snapshot, stuck_minutes: int) -> discord.Message:
        channel = self.client.get_channel(Config.DISCORD_MEDIA_ATTENTION_CHANNEL_ID)
        if channel is None:
            raise RuntimeError("Media attention channel not found.")
        return await channel.send(embed=MediaAttentionAlertView.build(alert, snapshot, stuck_minutes))

    async def update_media_attention_alert(self, message_id: int, alert, snapshot, stuck_minutes: int) -> bool | None:
        channel = self.client.get_channel(Config.DISCORD_MEDIA_ATTENTION_CHANNEL_ID)
        if channel is None:
            raise RuntimeError("Media attention channel not found.")
        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=MediaAttentionAlertView.build(alert, snapshot, stuck_minutes))
            return True
        except discord.NotFound:
            return False
        except discord.HTTPException as error:
            logger.warning("Unable to update media attention alert %s: %s", message_id, error)
            return None

    async def send_trending_movies(
        self,
        embed: discord.Embed,
    ) -> discord.Message:
        channel = self._get_trending_movies_channel()

        return await channel.send(embed=embed)

    async def send_upcoming_movies(self, embed: discord.Embed) -> discord.Message:
        return await self._get_trending_movies_channel().send(embed=embed)

    async def send_trending_tv(self, embed: discord.Embed) -> discord.Message:
        return await self._get_trending_tv_channel().send(embed=embed)

    async def trending_movies_message_exists(
        self,
        message_id: int,
    ) -> bool | None:
        channel = self._get_trending_movies_channel()

        try:
            await channel.fetch_message(message_id)

            return True

        except discord.NotFound:
            return False

        except discord.HTTPException as error:
            logger.warning(
                "Unable to fetch trending movies message %s: %s",
                message_id,
                error,
            )

            return None

    async def upcoming_movies_message_exists(self, message_id: int) -> bool | None:
        return await self.trending_movies_message_exists(message_id)

    async def trending_tv_message_exists(self, message_id: int) -> bool | None:
        return await self._message_exists(self._get_trending_tv_channel(), message_id)

    async def update_trending_movies(
        self,
        message_id: int,
        embed: discord.Embed,
    ) -> bool | None:
        channel = self._get_trending_movies_channel()

        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed)

            return True

        except discord.NotFound:
            return False

        except discord.HTTPException as error:
            logger.warning(
                "Unable to update trending movies message %s: %s",
                message_id,
                error,
            )

            return None

    async def update_upcoming_movies(
        self,
        message_id: int,
        embed: discord.Embed,
    ) -> bool | None:
        return await self.update_trending_movies(message_id, embed)

    async def update_trending_tv(
        self,
        message_id: int,
        embed: discord.Embed,
    ) -> bool | None:
        channel = self._get_trending_tv_channel()

        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=embed)
            return True
        except discord.NotFound:
            return False
        except discord.HTTPException as error:
            logger.warning("Unable to update trending TV message %s: %s", message_id, error)
            return None

    def _get_trending_movies_channel(self):
        channel_id = Config.DISCORD_TRENDING_MOVIES_CHANNEL_ID

        if channel_id is None:
            raise RuntimeError("Trending movies channel is not configured.")

        channel = self.client.get_channel(channel_id)

        if channel is None:
            raise RuntimeError("Trending movies channel not found.")

        return channel

    def _get_trending_tv_channel(self):
        channel_id = Config.DISCORD_TRENDING_TV_CHANNEL_ID

        if channel_id is None:
            raise RuntimeError("Trending TV channel is not configured.")

        channel = self.client.get_channel(channel_id)

        if channel is None:
            raise RuntimeError("Trending TV channel not found.")

        return channel

    @staticmethod
    async def _message_exists(channel, message_id: int) -> bool | None:
        try:
            await channel.fetch_message(message_id)
            return True
        except discord.NotFound:
            return False
        except discord.HTTPException as error:
            logger.warning("Unable to fetch dashboard message %s: %s", message_id, error)
            return None

    async def update_health_alert(
        self,
        message_id: int,
        issue: HealthIssue,
    ) -> bool | None:
        channel = self.client.get_channel(Config.DISCORD_MEDIA_ATTENTION_CHANNEL_ID)

        if channel is None:
            raise RuntimeError("Media attention channel not found.")

        try:
            message = await channel.fetch_message(message_id)
            await message.edit(embed=HealthAlertView.build(issue))

            return True

        except discord.NotFound:
            return False

        except discord.HTTPException as error:
            logger.warning(
                "Unable to update health alert %s: %s",
                message_id,
                error,
            )

            return None

    async def delete_health_alert(
        self,
        message_id: int,
    ) -> bool:
        channel = self.client.get_channel(Config.DISCORD_MEDIA_ATTENTION_CHANNEL_ID)

        if channel is None:
            raise RuntimeError("Media attention channel not found.")

        try:
            message = await channel.fetch_message(message_id)

            await message.delete()

            return True

        except discord.NotFound:
            return True

        except discord.HTTPException as error:
            logger.warning(
                "Unable to delete health alert %s: %s",
                message_id,
                error,
            )

            return False
