import discord

from models.media_result import MediaResult
from views.details_view import DetailsView


class MediaSelectionView(discord.ui.View):
    def __init__(
        self,
        results: list[MediaResult],
        requesting_user_id: int,
    ):
        super().__init__(timeout=300)

        self.requesting_user_id = requesting_user_id

        for index, result in enumerate(results[:10], start=1):
            button = discord.ui.Button(
                label=str(index),
                style=discord.ButtonStyle.secondary,
            )

            button.callback = self.create_callback(result)

            self.add_item(button)

    def create_callback(self, result: MediaResult):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.requesting_user_id:
                await interaction.response.send_message(
                    "Only the user who started this search can use these buttons.",
                    ephemeral=True,
                )
                return

            embed = DetailsView.build(result)

            await interaction.response.edit_message(
                embed=embed,
                view=None,
            )

        return callback