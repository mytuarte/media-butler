import discord

from models.media_result import MediaResult
from services.registry import services
from views.delete_confirmation_view import DeleteConfirmationView


class DeleteMediaView(discord.ui.View):
    def __init__(
        self,
        result: MediaResult,
        requesting_user_id: int,
    ):
        super().__init__(timeout=300)

        self.result = result
        self.requesting_user_id = requesting_user_id

    @discord.ui.button(
        label="Delete",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
    )
    async def delete_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if interaction.user.id != self.requesting_user_id:
            await interaction.response.send_message(
                "Only the user who started this command can delete media.",
                ephemeral=True,
            )
            return

        services.delete_confirmation.start_confirmation(
            interaction.user.id,
            self.result,
        )

        await interaction.response.edit_message(
            content=(
                "## ⚠️ Confirm Deletion\n\n"
                f"**{self.result.title} ({self.result.year})**\n\n"
                "This will permanently:\n"
                "• Remove from Radarr/Sonarr\n"
                "• Delete media files\n"
                "• Delete media folder (if empty)\n"
                "• Remove the Overseerr request\n\n"
                "**This cannot be undone.**\n\n"
                "Type **YES** within **60 seconds** to continue."
            ),
            embed=None,
            view=DeleteConfirmationView(
                requesting_user_id=self.requesting_user_id,
            ),
        )

    @discord.ui.button(
        label="Cancel",
        emoji="❌",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ):
        if interaction.user.id != self.requesting_user_id:
            await interaction.response.send_message(
                "Only the user who started this command can use these buttons.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            content="❌ Delete cancelled.",
            embed=None,
            view=None,
        )