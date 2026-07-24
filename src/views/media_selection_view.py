import asyncio
import discord
from services.log_service import logger

from models.media_result import MediaResult
from services.media_details_service import MediaDetailsService
from services.analyze_service import AnalyzeService
from views.analyze_view import AnalyzeView
from views.delete_media_view import DeleteMediaView
from views.details_view import DetailsView
from views.info_view import InfoView


class MediaSelectionView(discord.ui.View):
    def __init__(
        self,
        results: list[MediaResult],
        requesting_user_id: int,
        mode: str = "find",
    ):
        super().__init__(timeout=300)

        self.requesting_user_id = requesting_user_id
        self.mode = mode

        self.media_details = MediaDetailsService()
        self.analyze = AnalyzeService()

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

            view = None

            if self.mode == "analyze":
                if getattr(self, "_analyzing", False):
                    await interaction.response.send_message("Analysis is already in progress.", ephemeral=True)
                    return
                self._analyzing = True
                await interaction.response.defer()
                try:
                    analysis = await asyncio.to_thread(self.analyze.analyze, result)
                    embed = AnalyzeView.build(analysis)
                except Exception:
                    logger.exception("Media analysis failed")
                    await interaction.followup.send("❌ Analysis failed. Please try again later.", ephemeral=True)
                    return
                finally:
                    self._analyzing = False
            elif self.mode == "info":
                details = self.media_details.get_details(result)
                embed = InfoView.build(details)
            else:
                embed = DetailsView.build(result)

                if self.mode == "delete":
                    view = DeleteMediaView(
                        result=result,
                        requesting_user_id=self.requesting_user_id,
                    )

            if self.mode == "analyze":
                await interaction.edit_original_response(embed=embed, view=None)
            else:
                await interaction.response.edit_message(embed=embed, view=view)

        return callback