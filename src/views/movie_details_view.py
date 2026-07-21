import discord

from models.media_result import MediaResult
from services.butler_insights_service import ButlerInsightsService
from services.pipeline.pipeline_resolver import PipelineResolver


class MovieDetailsView:
    @staticmethod
    def build(result: MediaResult) -> discord.Embed:
        pipeline = PipelineResolver.resolve(result)
        insights = ButlerInsightsService.generate(result)

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

        if result.download:
            if result.download.state.lower() == "paused":
                download_text = (
                    f"⏸️ Paused\n"
                    f"{result.download.progress}%"
                )
            else:
                download_text = (
                    f"{result.download.progress}%\n"
                    f"ETA: {result.download.eta}"
                )

            embed.add_field(
                name="📥 Download",
                value=download_text,
                inline=True,
            )

        if pipeline.next_action:
            embed.add_field(
                name="➡️ Next",
                value=pipeline.next_action,
                inline=False,
            )

        if insights:
            embed.add_field(
                name="💡 Butler Insights",
                value="\n".join(
                    f"{insight.icon} {insight.message}"
                    for insight in insights
                ),
                inline=False,
            )

        embed.set_footer(text="Media Butler")

        return embed