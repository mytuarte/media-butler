from commands.delete_command import DeleteCommand
from commands.digital_command import DigitalCommand
from commands.find_command import FindCommand
from commands.help_command import HelpCommand
from commands.info_command import InfoCommand
from commands.ping_command import PingCommand
from commands.sab_command import SabCommand
from commands.scenario_command import ScenarioCommand
from commands.space_command import SpaceCommand
from commands.trending_command import TrendingCommand
from commands.trending_tv_command import TrendingTvCommand
from config import Config
from models.command_channel import CommandChannel
from services.log_service import logger
from services.registry import services
from views.delete_result_view import DeleteResultView


class CommandService:
    """
    Routes Discord messages to the appropriate command.
    """

    def __init__(self):
        self.commands = {}

        # Register commands
        self.register(PingCommand())
        self.register(FindCommand())
        self.register(InfoCommand())
        self.register(DeleteCommand())
        self.register(ScenarioCommand())
        self.register(SabCommand())
        self.register(SpaceCommand())
        self.register(TrendingCommand())
        self.register(TrendingTvCommand())
        self.register(DigitalCommand())

        self.register(HelpCommand(self.commands))

    def register(self, command):
        self.commands[command.COMMAND] = command

    def get_channel_type(self, channel_id):
        if channel_id == Config.DISCORD_ADMIN_CHANNEL_ID:
            return CommandChannel.ADMIN

        if channel_id == Config.DISCORD_MEDIA_SEARCH_CHANNEL_ID:
            return CommandChannel.MEDIA_SEARCH

        if channel_id == Config.DISCORD_CHANNEL_ID:
            return CommandChannel.GENERAL

        return None

    async def handle_message(self, message):
        # Ignore bots
        if message.author.bot:
            return

        channel = self.get_channel_type(message.channel.id)

        if channel is None:
            return

        #
        # MEDIA SEARCH
        #
        # Any non-command message becomes a !find command.
        #
        if channel == CommandChannel.MEDIA_SEARCH and not message.content.startswith(
            "!"
        ):
            message.content = f"!find {message.content}"

        content = message.content.strip()

        #
        # Handle pending delete confirmations
        #
        if content.upper() == "YES":
            media = services.delete_confirmation.confirm(
                message.author.id,
            )

            if media is not None:
                try:
                    result = services.delete.delete(media)

                    await message.channel.send(
                        embed=DeleteResultView.build(result),
                    )

                except NotImplementedError as ex:
                    await message.channel.send(f"⚠️ {ex}")

                except Exception as ex:
                    await message.channel.send(f"❌ Delete failed.\n\n`{ex}`")

                return

        if not content.startswith("!"):
            return

        command_name = content[1:].split()[0].lower()

        logger.info(f"Received command: {command_name}")

        command = self.commands.get(command_name)

        if command is None:
            await message.channel.send(
                f"Unknown command: `{command_name}`\n"
                "Type `!help` to see available commands."
            )
            return

        if channel not in command.CHANNELS:
            logger.info(f"Command '{command_name}' not allowed in {channel.name}")
            return

        await command.execute(message)
