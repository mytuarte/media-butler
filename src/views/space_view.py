import discord

from models.space_result import SpaceResult
from utils.formatting import format_size


class SpaceView:
    @staticmethod
    def build(result: SpaceResult):
        percent_used = 0

        if result.total_bytes > 0:
            percent_used = (
                result.used_bytes / result.total_bytes
            ) * 100

        managed_total = (
            result.movie_bytes +
            result.series_bytes
        )

        embed = discord.Embed(
            title="💾 Storage Summary",
            color=discord.Color.gold(),
        )

        embed.add_field(
            name="Capacity",
            value=format_size(result.total_bytes),
            inline=True,
        )

        embed.add_field(
            name="Used",
            value=(
                f"{format_size(result.used_bytes)} "
                f"({percent_used:.1f}%)"
            ),
            inline=True,
        )

        embed.add_field(
            name="Free",
            value=format_size(result.free_bytes),
            inline=True,
        )

        embed.add_field(
            name="Managed Media",
            value=(
                f"Movies: **{result.movie_count}** "
                f"({format_size(result.movie_bytes)})\n"
                f"Series: **{result.series_count}** "
                f"({format_size(result.series_bytes)})\n\n"
                f"Managed Total: "
                f"**{format_size(managed_total)}**"
            ),
            inline=False,
        )

        embed.set_footer(
            text="Media Butler"
        )

        return embed