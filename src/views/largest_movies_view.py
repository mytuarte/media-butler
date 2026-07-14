import discord

from models.space_result import SpaceResult
from utils.formatting import format_size


class LargestMoviesView:
    @staticmethod
    def build(result: SpaceResult):
        embed = discord.Embed(
            title="🎬 Largest Movies",
            color=discord.Color.gold(),
        )

        if not result.largest_movies:
            embed.description = "No movies found."

            embed.set_footer(
                text="Media Butler"
            )

            return embed

        lines = []

        for index, movie in enumerate(
            result.largest_movies,
            start=1,
        ):
            lines.append(
                f"`{index:>2}.` "
                f"**{movie.title}**\n"
                f"      {format_size(movie.size_bytes)}"
            )

        embed.description = "\n\n".join(lines)

        embed.set_footer(
            text="Media Butler"
        )

        return embed