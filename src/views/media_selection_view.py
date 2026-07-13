import discord

from models.media_result import MediaResult


class MediaSelectionView(discord.ui.View):
    def __init__(self, results: list[MediaResult]):
        super().__init__(timeout=300)

        for index, result in enumerate(results[:10], start=1):
            button = discord.ui.Button(
                label=str(index),
                style=discord.ButtonStyle.secondary,
            )

            button.callback = self.create_callback(result)

            self.add_item(button)

    def create_callback(self, result: MediaResult):
        async def callback(interaction: discord.Interaction):
            await interaction.response.send_message(
                f"You selected **{result.title} ({result.year})**",
                ephemeral=True,
            )

        return callback