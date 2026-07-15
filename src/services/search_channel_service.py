import asyncio

import discord

from config import Config
from models.command_channel import CommandChannel


class SearchChannelService:
    async def cleanup(
        self,
        *,
        channel: CommandChannel,
        user_message: discord.Message,
        bot_message: discord.Message,
    ) -> None:
        if channel != CommandChannel.MEDIA_SEARCH:
            return

        await self._delete_user_message(user_message)

        await asyncio.sleep(Config.SEARCH_RESULT_LIFETIME_SECONDS)

        await self._delete_bot_message(bot_message)

    async def _delete_user_message(
        self,
        message: discord.Message,
    ) -> None:
        if not Config.DELETE_SEARCH_MESSAGES:
            return

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
        ):
            pass

    async def _delete_bot_message(
        self,
        message: discord.Message,
    ) -> None:
        if not Config.DELETE_SEARCH_RESULTS:
            return

        try:
            await message.delete()

        except (
            discord.Forbidden,
            discord.NotFound,
        ):
            pass
