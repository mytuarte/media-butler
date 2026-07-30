import asyncio
import discord

from models.downgrade import ReplacementCandidate
from services.downgrade_operation_service import (
    DowngradeOperationService, DuplicateDowngrade, RadarrRejected, ReleaseUnavailable,
)
from services.log_service import logger
from views.analyze_view import format_bytes


class DowngradeView(discord.ui.View):
    def __init__(self, title, current_size, current_quality, candidates, requesting_user_id, media_id=None, media_type="movie", operation=None):
        super().__init__(timeout=300)
        self.title, self.current_size, self.current_quality = title, current_size, current_quality
        self.candidates, self.requesting_user_id = candidates, requesting_user_id
        self.media_id, self.media_type = media_id, media_type
        self.operation = operation
        for number, candidate in enumerate(candidates, start=1):
            button = discord.ui.Button(label=str(number), style=discord.ButtonStyle.secondary)
            button.callback = self._candidate_callback(candidate)
            self.add_item(button)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel.callback = self._cancel
        self.add_item(cancel)

    @staticmethod
    def build(title, current_size, current_quality, candidates):
        embed = discord.Embed(title="♻ Replacement Candidates", description=title)
        embed.add_field(name="Current", value=f"{format_bytes(current_size)}\n{current_quality or 'Unknown'}", inline=False)
        if candidates:
            lines = []
            for number, candidate in enumerate(candidates, 1):
                quality = candidate.quality or "Unknown"
                lines.append(f"**{number}. {format_bytes(candidate.size_bytes)}**\n{quality}\n{candidate.video_codec or 'Unknown codec'} · {', '.join(candidate.languages) or 'Unknown languages'}\nSaves {format_bytes(candidate.savings_bytes)} ({candidate.savings_percent}%)")
            embed.add_field(name="Candidates", value="\n\n".join(lines), inline=False)
        else:
            embed.add_field(name="Candidates", value="No acceptable smaller releases found.", inline=False)
        return embed

    def _candidate_callback(self, candidate):
        async def callback(interaction):
            if interaction.user.id != self.requesting_user_id:
                await interaction.response.send_message("Only the user who started this search can use these buttons.", ephemeral=True)
                return
            await interaction.response.edit_message(embed=self.confirmation_embed(self.title, self.current_size, self.current_quality, candidate), view=DowngradeConfirmationView(self, candidate))
        return callback

    async def _cancel(self, interaction):
        await interaction.response.edit_message(content="Downgrade discovery cancelled.", embed=None, view=None)

    @staticmethod
    def confirmation_embed(title, current_size, current_quality, candidate):
        embed = discord.Embed(title=f"Replace {title}?")
        embed.add_field(name="Current", value=f"{format_bytes(current_size)}\n{current_quality or 'Unknown'}", inline=False)
        embed.add_field(name="New", value=f"{format_bytes(candidate.size_bytes)}\n{candidate.quality or 'Unknown'}", inline=False)
        embed.add_field(name="Release", value=candidate.release_name or "Unknown", inline=False)
        embed.add_field(name="Recover", value=format_bytes(candidate.savings_bytes), inline=False)
        return embed

    @staticmethod
    def status_embed(title, candidate, status):
        embed = discord.Embed(title="♻ Replacement Status", description=title)
        embed.add_field(name="Status", value=status, inline=False)
        embed.add_field(name="Selected", value=f"{format_bytes(candidate.size_bytes)}\n{candidate.quality or 'Unknown'}\n{candidate.video_codec or 'Unknown'}\n{', '.join(candidate.languages) or 'Unknown'}", inline=False)
        embed.add_field(name="Expected Savings", value=format_bytes(candidate.savings_bytes), inline=False)
        return embed

    @staticmethod
    def started_embed(title, candidate, downloader=None):
        embed = discord.Embed(title="⬇️ Replacement Download Started", description=f"{title}\n\n{format_bytes(candidate.size_bytes)}\n{candidate.quality or 'Unknown'}\n{candidate.video_codec or 'Unknown'}\n{', '.join(candidate.languages) or 'Unknown'}")
        if downloader:
            embed.add_field(name="Downloader", value=downloader, inline=False)
        embed.add_field(name="Expected Savings", value=format_bytes(candidate.savings_bytes), inline=False)
        return embed


class DowngradeConfirmationView(discord.ui.View):
    def __init__(self, parent, candidate):
        super().__init__(timeout=300)
        self.parent, self.candidate, self._submitted = parent, candidate, False
        confirm = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.primary)
        confirm.callback = self.confirm
        self.add_item(confirm)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel.callback = self.cancel
        self.add_item(cancel)

    async def confirm(self, interaction):
        if interaction.user.id != self.parent.requesting_user_id:
            await interaction.response.send_message("Only the user who started this search can use these buttons.", ephemeral=True)
            return
        if self._submitted:
            await interaction.response.send_message("This replacement has already been submitted.", ephemeral=True)
            return
        self._submitted = True
        for item in self.children:
            item.disabled = True
        if self.parent.media_type == "series":
            await interaction.response.edit_message(content="TV replacement downloads are not currently supported.", embed=None, view=self)
            return
        await interaction.response.edit_message(embed=DowngradeView.status_embed(self.parent.title, self.candidate, "Submitting selected release to Radarr..."), view=self)
        loop = asyncio.get_running_loop()
        operation = self.parent.operation
        async def edit_state(state):
            labels = {"waiting": "Submitted to Radarr. Waiting for download queue...", "queued": "Queued for download"}
            await interaction.edit_original_response(embed=DowngradeView.status_embed(self.parent.title, self.candidate, labels[state]), view=None)
        def status(state):
            asyncio.run_coroutine_threadsafe(edit_state(state), loop).result(timeout=10)
        try:
            if operation is None:
                raise RuntimeError("Downgrade operation service is unavailable")
            outcome = await asyncio.to_thread(operation.run, self.parent.media_id, self.candidate, status)
            if outcome.state == "downloading":
                embed = DowngradeView.started_embed(self.parent.title, self.candidate, outcome.downloader)
            else:
                embed = discord.Embed(title="⚠️ Replacement Submitted", description="Radarr accepted the selected release, but Media Butler did not confirm that the download started within the expected time.\n\nThe original movie remains untouched.")
        except ReleaseUnavailable:
            embed = discord.Embed(title="❌ Replacement Not Available", description="The selected release is no longer present in Radarr's manual search.\n\nThe original movie remains untouched.")
        except RadarrRejected:
            embed = discord.Embed(title="❌ Replacement Failed", description="Radarr rejected the selected release.\n\nThe original movie remains untouched.")
        except DuplicateDowngrade:
            embed = discord.Embed(title="❌ Replacement Failed", description="A replacement operation is already active for this movie.\n\nThe original movie remains untouched.")
        except Exception:
            logger.exception("Unexpected downgrade submission failure for Radarr movie %s", self.parent.media_id)
            embed = discord.Embed(title="❌ Replacement Failed", description="Media Butler could not start the selected replacement.\n\nThe original movie remains untouched.")
        await interaction.edit_original_response(embed=embed, view=None)

    async def cancel(self, interaction):
        await interaction.response.edit_message(embed=DowngradeView.build(self.parent.title, self.parent.current_size, self.parent.current_quality, self.parent.candidates), view=self.parent)
