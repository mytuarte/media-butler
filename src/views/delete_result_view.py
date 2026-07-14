import discord

from models.delete_result import DeleteResult


class DeleteResultView:
    @staticmethod
    def build(result: DeleteResult):
        embed = discord.Embed(
            title="✅ Delete Complete",
            description=result.media_title,
            color=discord.Color.green(),
        )

        if result.radarr_deleted:
            embed.add_field(
                name="Radarr",
                value="✅ Removed",
                inline=True,
            )

        if result.sonarr_deleted:
            embed.add_field(
                name="Sonarr",
                value="✅ Removed",
                inline=True,
            )

        if result.files_deleted:
            embed.add_field(
                name="Media Files",
                value="✅ Deleted",
                inline=True,
            )

        if result.overseerr_deleted:
            embed.add_field(
                name="Overseerr",
                value="✅ Removed",
                inline=True,
            )

        if result.plex_watchlist_deleted:
            embed.add_field(
                name="Plex Watchlist",
                value="✅ Removed",
                inline=True,
            )

        embed.set_footer(
            text="Media Butler"
        )

        return embed