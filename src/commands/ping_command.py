class PingCommand:
    """
    Simple command used to verify the bot is responding.
    """

    COMMAND = "ping"
    DESCRIPTION = "Tests whether the bot is responding."

    async def execute(self, message):
        await message.channel.send("Pong!")
