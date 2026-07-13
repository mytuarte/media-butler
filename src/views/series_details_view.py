import discord

from models.media_result import MediaResult
from models.series_status import SeriesStatus


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
        series_status = SeriesStatus.from_result(result)

        embed = discord.Embed(
            title=f"📺 {result.title} ({result.year})",
            color=series_status.color,
        )

        embed.add_field(
            name="Status",
            value=series_status.display,
            inline=False,
        )

        embed.add_field(
            name="Progress",
            value=(
                f"{result.downloaded_episodes} / "
                f"{result.total_episodes} Episodes"
            ),
            inline=False,
        )

        embed.add_field(
            name="Seasons",
            value=SeriesDetailsView._format_seasons(result),
            inline=False,
        )

        embed.set_footer(text="Media Butler")

        return embed