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

        lines = [f'**Search:** "{query}"', ""]

        for index, result in enumerate(shown_results, start=1):
            year = f" ({result.year})" if result.year else ""

            icon = "🎬"

            if result.media_type == "series":
                icon = "📺"

            lines.append(
                f"{index}. {icon} {result.title}{year}"
            )

        embed = discord.Embed(
            title="🔍 Search Results",
            description="\n".join(lines),
            color=discord.Color.blue(),
        )

        if len(results) > SearchResultsView.MAX_RESULTS:
            footer = (
                f"Showing {SearchResultsView.MAX_RESULTS} "
                f"of {len(results)} results"
            )
        else:
            count = len(results)
            footer = (
                f"Showing {count} result"
                if count == 1
                else f"Showing {count} results"
            )

        embed.set_footer(text=footer)

        return embed