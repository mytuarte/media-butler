from commands.delete_command import DeleteCommand
from commands.find_command import FindCommand
from commands.help_command import HelpCommand
from commands.info_command import InfoCommand
from commands.ping_command import PingCommand
from commands.sab_command import SabCommand
from commands.scenario_command import ScenarioCommand
from commands.space_command import SpaceCommand
from config import Config
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
        self.commands[PingCommand.COMMAND] = PingCommand()
        self.commands[FindCommand.COMMAND] = FindCommand()
        self.commands[InfoCommand.COMMAND] = InfoCommand()
        self.commands[DeleteCommand.COMMAND] = DeleteCommand()
        self.commands[ScenarioCommand.COMMAND] = ScenarioCommand()
        self.commands[SabCommand.COMMAND] = SabCommand()
        self.commands[SpaceCommand.COMMAND] = SpaceCommand()
        self.commands[HelpCommand.COMMAND] = HelpCommand(self.commands)

    async def handle_message(self, message):
        # Ignore bots (including ourselves)
        if message.author.bot:
            return

        # Only allow commands in approved channels
        channel_id = message.channel.id
        logger.info(f"Channel ID: {channel_id}")

        if channel_id == Config.DISCORD_ADMIN_CHANNEL_ID:
            allowed_commands = set(self.commands.keys())
        elif channel_id == Config.DISCORD_MEDIA_STATUS_CHANNEL_ID:
            allowed_commands = {FindCommand.COMMAND}
        else:
            return

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
                    await message.channel.send(
                        f"⚠️ {ex}"
                    )

                except Exception as ex:
                    await message.channel.send(
                        f"❌ Delete failed.\n\n`{ex}`"
                    )

                return

        # Ignore anything that isn't a command
        if not content.startswith("!"):
            return

        # Remove the "!"
        command_name = content[1:].split()[0].lower()

        logger.info(f"Received command: {command_name}")

        if command_name not in allowed_commands:
            return

        command = self.commands.get(command_name)

        if command is None:
            await message.channel.send(
                f"Unknown command: `{command_name}`\n"
                "Type `!help` to see available commands."
            )
            return

        await command.execute(message)