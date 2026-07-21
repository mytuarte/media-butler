import discord


class DeleteConfirmationView(discord.ui.View):
    def __init__(
        self,
        requesting_user_id: int,
    ):
        super().__init__(timeout=60)

        self.requesting_user_id = requesting_user_id

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