from models.command_channel import CommandChannel


class PingCommand:
    """
    Simple health check command.
    """

    COMMAND = "ping"
    DESCRIPTION = "Tests whether the bot is online."

    CHANNELS = {
        CommandChannel.ADMIN,
    }

    async def execute(self, message):
        await message.channel.send("Pong!")