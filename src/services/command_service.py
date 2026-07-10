from commands.ping_command import PingCommand
from services.log_service import logger


class CommandService:
    """
    Routes Discord messages to the appropriate command.
    """

    def __init__(self):
        self.commands = {
            PingCommand.COMMAND: PingCommand(),
        }

    async def handle_message(self, message):
        # Ignore bots (including ourselves)
        if message.author.bot:
            return

        content = message.content.strip()

        # Ignore anything that isn't a command
        if not content.startswith("!"):
            return

        # Remove the "!"
        command_name = content[1:].split()[0].lower()

        logger.info(f"Received command: {command_name}")

        command = self.commands.get(command_name)

        if command is None:
            await message.channel.send(
                f"Unknown command: `{command_name}`\n"
                "Type `!help` to see available commands."
            )
            return

        await command.execute(message)