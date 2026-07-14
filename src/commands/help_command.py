import discord

from config import Config
from models.command_channel import CommandChannel


class HelpCommand:
    """
    Displays all available commands.
    """

    COMMAND = "help"
    DESCRIPTION = "Displays all available commands."

    CHANNELS = {
        CommandChannel.ADMIN,
        CommandChannel.GENERAL,
    }

    def __init__(self, commands):
        self.commands = commands

    def _get_channel_type(self, channel_id):
        if channel_id == Config.DISCORD_ADMIN_CHANNEL_ID:
            return CommandChannel.ADMIN

        if channel_id == Config.DISCORD_MEDIA_STATUS_CHANNEL_ID:
            return CommandChannel.GENERAL

        return None

    async def execute(self, message):
        channel = self._get_channel_type(
            message.channel.id
        )

        embed = discord.Embed(
            title="🤖 Media Butler Commands",
            color=0x3498DB,
        )

        commands = sorted(
            self.commands.values(),
            key=lambda command: command.COMMAND,
        )

        for command in commands:
            if channel not in command.CHANNELS:
                continue

            embed.add_field(
                name=f"!{command.COMMAND}",
                value=command.DESCRIPTION,
                inline=False,
            )

        embed.set_footer(
            text="Media Butler"
        )

        await message.channel.send(
            embed=embed,
        )