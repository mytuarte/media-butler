import discord

from models.media_details import MediaDetails
from utils.formatting import (
    format_age,
    format_date,
    format_size,
)


class InfoView:
    @staticmethod
    def build(details: MediaDetails):
        media = details.media

        embed = discord.Embed(
            title=f"{media.title} ({media.year})",
            color=discord.Color.blurple(),
        )

        embed.add_field(
            name="Status",
            value=(
                f"Available: {'✅ Yes' if media.has_file else '❌ No'}\n"
                f"Monitored: {'✅ Yes' if media.monitored else '❌ No'}"
            ),
            inline=True,
        )

        embed.add_field(
            name="Media",
            value=(
                f"Quality: {media.quality}"
            ),
            inline=True,
        )

        embed.add_field(
            name="Storage",
            value=(
                f"Size: {format_size(details.size_bytes)}\n"
                f"Added: {format_date(details.added_date)}\n"
                f"On Server: {format_age(details.added_date)}"
            ),
            inline=False,
        )

        embed.add_field(
            name="Request",
            value=(
                f"👤 {details.requester or 'Manual / Unknown'}\n"
                f"📅 {format_date(details.requested_date)}"
            ),
            inline=False,
        )

        if details.path:
            embed.add_field(
                name="Path",
                value=f"`{details.path}`",
                inline=False,
            )

        embed.add_field(
            name="Technical",
            value=(
                f"TMDb: {media.tmdb_id or 'Unknown'}\n"
                f"Radarr ID: {media.id}"
            ),
            inline=False,
        )

        embed.set_footer(
            text="Media Butler"
        )

        return embed