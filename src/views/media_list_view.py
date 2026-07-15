import discord

from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState


class MediaListView:
    @staticmethod
    def build(
        title: str,
        media: list[DiscoveryItem],
    ):
        embed = discord.Embed(
            title=title,
            color=discord.Color.orange(),
        )

        if not media:
            embed.description = "No media found."
            embed.set_footer(text="🟢 Available • 🟡 Monitored • ⚪ Not Added")
            return embed

        media = sorted(
            media,
            key=MediaListView._sort_key,
        )

        lines = []

        for item in media:
            icon = MediaListView._status_icon(item)

            line = f"{icon} {item.title}"

            if item.status_detail:
                line += f" ({item.status_detail})"

            lines.append(line)

        embed.description = "\n".join(lines)

        embed.set_footer(text="🟢 Available • 🟡 Monitored • ⚪ Not Added")

        return embed

    @staticmethod
    def _status_icon(
        item: DiscoveryItem,
    ) -> str:
        match item.monitoring_state:
            case MonitoringState.AVAILABLE:
                return "🟢"

            case MonitoringState.COMING_SOON:
                return "🟡"

            case MonitoringState.DOWNLOADING:
                return "⬇️"

            case _:
                return "⚪"

    @staticmethod
    def _sort_key(
        item: DiscoveryItem,
    ) -> tuple[int]:
        match item.monitoring_state:
            case MonitoringState.AVAILABLE:
                return (0,)

            case MonitoringState.DOWNLOADING:
                return (1,)

            case MonitoringState.COMING_SOON:
                return (2,)

            case _:
                return (3,)
