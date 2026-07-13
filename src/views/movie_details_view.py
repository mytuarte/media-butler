import discord

from models.media_result import MediaResult
from services.pipeline.pipeline_resolver import PipelineResolver


class MovieDetailsView:
    @staticmethod
    def build(result: MediaResult) -> discord.Embed:
        pipeline = PipelineResolver.resolve(result)

        monitoring = "Enabled" if result.monitored else "Disabled"

        availability = {
            "announced": "Announced",
            "inCinemas": "In Theaters",
            "released": "Released",
        }.get(
            result.status,
            result.status.replace("_", " ").title(),
        )

        embed = discord.Embed(
            title=f"🎬 {result.title} ({result.year})",
            color=pipeline.state.color,
        )

        embed.description = (
            f"{pipeline.state.display}\n"
            f"{pipeline.message}"
        )

        if pipeline.requester:
            embed.add_field(
                name="👤 Requested By",
                value=pipeline.requester,
                inline=True,
            )

        if pipeline.requested_date:
            embed.add_field(
                name="📅 Requested",
                value=pipeline.requested_date,
                inline=True,
            )

        embed.add_field(
            name="🎞️ Quality",
            value=result.quality,
            inline=True,
        )

        embed.add_field(
            name="📺 Availability",
            value=availability,
            inline=True,
        )

        embed.add_field(
            name="👁️ Monitoring",
            value=monitoring,
            inline=True,
        )

        if pipeline.next_action:
            embed.add_field(
                name="➡️ Next",
                value=pipeline.next_action,
                inline=False,
            )

        embed.set_footer(text="Media Butler")

        return embed