import discord

from models.space_result import SpaceResult
from utils.formatting import format_size


class SpaceView:
    @staticmethod
    def build(result: SpaceResult):
        total_size = (
            result.movie_size_bytes +
            result.series_size_bytes
        )

        embed = discord.Embed(
            title="💾 Storage Summary",
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="Movies",
            value=(
                f"{result.movie_count} Movies\n"
                f"{format_size(result.movie_size_bytes)}"
            ),
            inline=True,
        )

        embed.add_field(
            name="Series",
            value=(
                f"{result.series_count} Series\n"
                f"{format_size(result.series_size_bytes)}"
            ),
            inline=True,
        )

        embed.add_field(
            name="Total",
            value=format_size(total_size),
            inline=False,
        )

        embed.set_footer(
            text="Media Butler"
        )

        return embed