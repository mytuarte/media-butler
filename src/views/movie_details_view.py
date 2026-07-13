import discord

from models.media_result import MediaResult
from models.media_status import MediaStatus


class MovieDetailsView:
    @staticmethod
    def build(result: MediaResult) -> discord.Embed:
        media_status = MediaStatus.from_result(result)

        monitoring = "Enabled" if result.monitored else "Disabled"

        availability = {
            "announced": "Announced",
            "inCinemas": "In Theaters",
            "released": "Released",
        }.get(result.status, result.status.replace("_", " ").title())

        embed = discord.Embed(
            title=f"🎬 {result.title} ({result.year})",
            color=media_status.color,
        )

        embed.add_field(
            name="Status",
            value=media_status.display,
            inline=False,
        )

        embed.add_field(
            name="Quality",
            value=result.quality,
            inline=False,
        )

        embed.add_field(
            name="Availability",
            value=availability,
            inline=False,
        )

        embed.add_field(
            name="Monitoring",
            value=monitoring,
            inline=False,
        )

        embed.set_footer(text="Media Butler")

        return embed