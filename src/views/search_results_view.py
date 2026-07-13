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

    MAX_RESULTS = 10

    @staticmethod
    def build(query: str, results: list[MediaResult]) -> discord.Embed:
        shown_results = results[: SearchResultsView.MAX_RESULTS]

        embed = discord.Embed(
            title="🎬 Search Results",
            description=f'Search results for **"{query}"**',
            color=discord.Color.blue(),
        )

        lines = []

        for index, result in enumerate(shown_results, start=1):
            year = f" ({result.year})" if result.year else ""
            lines.append(f"**{index}.** {result.title}{year}")

        embed.add_field(
            name="Results",
            value="\n".join(lines),
            inline=False,
        )

        if len(results) > SearchResultsView.MAX_RESULTS:
            footer = (
                f"Showing {SearchResultsView.MAX_RESULTS} "
                f"of {len(results)} results."
            )
        else:
            footer = f"Showing {len(results)} result(s)."

        embed.set_footer(text=footer)

        return embed