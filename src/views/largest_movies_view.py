import discord

from models.space_result import SpaceResult
from utils.formatting import format_size


class LargestMoviesView:
    MAX_TITLE_LENGTH = 42

    @classmethod
    def _truncate(cls, title: str) -> str:
        if len(title) <= cls.MAX_TITLE_LENGTH:
            return title

        return title[: cls.MAX_TITLE_LENGTH - 3] + "..."

    @classmethod
    def build(cls, result: SpaceResult):
        embed = discord.Embed(
            title="🎬 Top 20 Largest Movies",
            color=discord.Color.gold(),
        )

        if not result.largest_movies:
            embed.description = "No movies found."

            embed.set_footer(
                text="Media Butler"
            )

            return embed

        lines = [
            "```",
            "#  Size       Movie",
            "────────────────────────────────────────────────────────",
        ]

        for index, movie in enumerate(
            result.largest_movies,
            start=1,
        ):
            title = cls._truncate(movie.title)
            size = format_size(movie.size_bytes)

            lines.append(
                f"{index:>2} {size:>9}  {title}"
            )

        lines.append("```")

        embed.description = "\n".join(lines)

        embed.set_footer(
            text="Media Butler"
        )

        return embed