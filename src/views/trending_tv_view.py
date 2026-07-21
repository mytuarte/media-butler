import discord

from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState


class TrendingTvView:
    """Builds the current digital TV popularity dashboard."""

    TITLE = "📺 Trending TV Shows Right Now"
    FOOTER_LEGEND = "🟢 Available · 🟡 Requested · ⚪ Not Requested"

    @classmethod
    def build(cls, shows: list[DiscoveryItem]) -> discord.Embed:
        embed = discord.Embed(title=cls.TITLE, color=discord.Color.blue())

        if shows:
            embed.description = "\n".join(
                f"{cls.status_icon(show)} {show.title}" for show in shows
            )
        else:
            embed.description = "No trending TV shows found."

        embed.set_footer(text=cls.FOOTER_LEGEND)
        return embed

    @staticmethod
    def status_icon(show: DiscoveryItem) -> str:
        if show.monitoring_state == MonitoringState.AVAILABLE:
            return "🟢"
        if show.monitoring_state != MonitoringState.NOT_ADDED or show.requester is not None:
            return "🟡"
        return "⚪"

    @classmethod
    def status(cls, show: DiscoveryItem) -> str:
        return {
            "🟢": "available",
            "🟡": "requested",
            "⚪": "not_requested",
        }[cls.status_icon(show)]
