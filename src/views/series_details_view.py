import discord

from models.media_result import MediaResult
from services.butler_insights_service import ButlerInsightsService
from services.pipeline.pipeline_resolver import PipelineResolver


class SeriesDetailsView:
    @staticmethod
    def _format_seasons(result: MediaResult) -> str:
        lines = []

        complete_start = None
        complete_end = None

        empty_start = None
        empty_end = None

        def append_range(emoji: str, start: int, end: int):
            if start is None:
                return

            if start == end:
                lines.append(f"{emoji} S{start}")
            else:
                lines.append(f"{emoji} S{start}–S{end}")

        for season in result.season_statuses:
            if not season.is_released:
                continue

            if season.is_complete:
                append_range("❌", empty_start, empty_end)
                empty_start = empty_end = None

                if complete_start is None:
                    complete_start = complete_end = season.season_number
                else:
                    complete_end = season.season_number

                continue

            if season.is_empty:
                append_range("✅", complete_start, complete_end)
                complete_start = complete_end = None

                if empty_start is None:
                    empty_start = empty_end = season.season_number
                else:
                    empty_end = season.season_number

                continue

            append_range("✅", complete_start, complete_end)
            append_range("❌", empty_start, empty_end)

            complete_start = complete_end = None
            empty_start = empty_end = None

            lines.append(season.display)

        append_range("✅", complete_start, complete_end)
        append_range("❌", empty_start, empty_end)

        if not lines:
            lines.append("📅 No released seasons")

        return "\n".join(lines)

    @staticmethod
    def build(result: MediaResult) -> discord.Embed:
        pipeline = PipelineResolver.resolve(result)
        insights = ButlerInsightsService.generate(result)

        embed = discord.Embed(
            title=f"📺 {result.title} ({result.year})",
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
            name="📺 Released",
            value=(
                pipeline.progress
                or (
                    f"{result.downloaded_episodes} / "
                    f"{result.total_episodes} Episodes"
                )
            ),
            inline=True,
        )

        embed.add_field(
            name="👁️ Monitoring",
            value="Enabled" if result.monitored else "Disabled",
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

        embed.add_field(
            name="🗂️ Seasons",
            value=SeriesDetailsView._format_seasons(result),
            inline=False,
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