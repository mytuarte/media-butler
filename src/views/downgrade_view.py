import discord
from models.downgrade import ReplacementCandidate
from views.analyze_view import format_bytes


class DowngradeView(discord.ui.View):
    """Candidate and confirmation UI; Phase 1 intentionally has no write action."""
    def __init__(self, title, current_size, current_quality, candidates, requesting_user_id):
        super().__init__(timeout=300)
        self.title, self.current_size, self.current_quality = title, current_size, current_quality
        self.candidates, self.requesting_user_id = candidates, requesting_user_id
        for number, candidate in enumerate(candidates, start=1):
            button = discord.ui.Button(label=str(number), style=discord.ButtonStyle.secondary)
            button.callback = self._candidate_callback(candidate)
            self.add_item(button)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel.callback = self._cancel
        self.add_item(cancel)

    @staticmethod
    def build(title, current_size, current_quality, candidates):
        embed = discord.Embed(title="♻ Replacement Candidates")
        embed.add_field(name="Current", value=f"{format_bytes(current_size)}\n{current_quality or 'Unknown'}", inline=False)
        if candidates:
            lines = []
            for number, candidate in enumerate(candidates, 1):
                quality = " ".join(value for value in (candidate.quality, candidate.resolution) if value) or "Unknown"
                lines.append(f"**{number}. {format_bytes(candidate.size_bytes)}**\n{quality}\n{candidate.video_codec or 'Unknown codec'} · {', '.join(candidate.languages) or 'Unknown languages'}\nSaves {format_bytes(candidate.savings_bytes)} ({candidate.savings_percent}%)")
            embed.add_field(name="Candidates", value="\n\n".join(lines), inline=False)
        else:
            embed.add_field(name="Candidates", value="No acceptable smaller releases found.", inline=False)
        return embed

    def _candidate_callback(self, candidate):
        async def callback(interaction):
            if interaction.user.id != self.requesting_user_id:
                await interaction.response.send_message("Only the user who started this search can use these buttons.", ephemeral=True); return
            await interaction.response.edit_message(embed=self.confirmation_embed(self.title, self.current_size, self.current_quality, candidate), view=DowngradeConfirmationView(self, candidate))
        return callback

    async def _cancel(self, interaction):
        await interaction.response.edit_message(content="Downgrade discovery cancelled.", embed=None, view=None)

    @staticmethod
    def confirmation_embed(title, current_size, current_quality, candidate):
        quality = " ".join(value for value in (candidate.quality, candidate.resolution) if value) or "Unknown"
        embed = discord.Embed(title=f"Replace {title}?")
        embed.add_field(name="Current", value=f"{format_bytes(current_size)}\n{current_quality or 'Unknown'}", inline=False)
        embed.add_field(name="New", value=f"{format_bytes(candidate.size_bytes)}\n{quality}", inline=False)
        embed.add_field(name="Recover", value=format_bytes(candidate.savings_bytes), inline=False)
        return embed


class DowngradeConfirmationView(discord.ui.View):
    def __init__(self, parent, candidate):
        super().__init__(timeout=300); self.parent = parent; self.candidate = candidate
        confirm = discord.ui.Button(label="Confirm", style=discord.ButtonStyle.primary)
        confirm.callback = self.confirm; self.add_item(confirm)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary)
        cancel.callback = self.cancel; self.add_item(cancel)

    async def confirm(self, interaction):
        if interaction.user.id != self.parent.requesting_user_id:
            await interaction.response.send_message("Only the user who started this search can use these buttons.", ephemeral=True); return
        await interaction.response.send_message("Download workflow not implemented yet.", ephemeral=True)

    async def cancel(self, interaction):
        await interaction.response.edit_message(embed=DowngradeView.build(self.parent.title, self.parent.current_size, self.parent.current_quality, self.parent.candidates), view=self.parent)
