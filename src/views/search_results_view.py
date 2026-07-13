import discord

from models.media_result import MediaResult


class SearchResultsView:
    """
    Builds Discord embeds for media search results.

    Future versions of this class will also own:
    - Result buttons
    - Pagination
    - Selection menus
    """

    @staticmethod
    def build(result: MediaResult) -> discord.Embed:
        status = "Downloaded" if result.has_file else "Missing"
        monitored = "Yes" if result.monitored else "No"

        embed = discord.Embed(
            title=f"🎬 {result.title} ({result.year})",
            color=0x2ECC71 if result.has_file else 0xE74C3C,
        )

        embed.add_field(
            name="Status",
            value=status,
            inline=False,
        )

        embed.add_field(
            name="Quality",
            value=result.quality,
            inline=False,
        )

        embed.add_field(
            name="Monitored",
            value=monitored,
            inline=False,
        )

        embed.set_footer(text="Media Butler")

        return embed