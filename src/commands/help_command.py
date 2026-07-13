import discord


class HelpCommand:
    """
    Displays all available commands.
    """

    COMMAND = "help"
    DESCRIPTION = "Displays all available commands."

    def __init__(self, commands):
        self.commands = commands

    async def execute(self, message):
        embed = discord.Embed(
            title="🤖 Media Butler Commands",
            color=0x3498DB,
        )

        for command in sorted(
            self.commands.values(),
            key=lambda command: command.COMMAND,
        ):
            embed.add_field(
                name=f"!{command.COMMAND}",
                value=command.DESCRIPTION,
                inline=False,
            )

        embed.set_footer(text="Media Butler")

        await message.channel.send(embed=embed)