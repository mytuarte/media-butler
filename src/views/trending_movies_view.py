import discord

from models.discovery.discovery_item import DiscoveryItem
from models.monitoring_state import MonitoringState


class TrendingMoviesView:
    """Builds the popularity dashboard without release-calendar messaging."""

    TITLE = "🔥 Trending Movies Right Now"
    FOOTER_LEGEND = "🟢 Available · 🟡 Requested · ⚪ Not Requested"

    @classmethod
    def build(cls, movies: list[DiscoveryItem]) -> discord.Embed:
        embed = discord.Embed(title=cls.TITLE, color=discord.Color.orange())

        if movies:
            embed.description = "\n".join(
                f"{cls.status_icon(movie)} {movie.title}" for movie in movies
            )
        else:
            embed.description = "No trending movies found."

        embed.set_footer(text=cls.FOOTER_LEGEND)
        return embed

    @staticmethod
    def status_icon(movie: DiscoveryItem) -> str:
        if movie.monitoring_state == MonitoringState.AVAILABLE:
            return "🟢"
        if (
            movie.monitoring_state != MonitoringState.NOT_ADDED
            or movie.requester is not None
        ):
            return "🟡"
        return "⚪"

    @classmethod
    def status(cls, movie: DiscoveryItem) -> str:
        """Return the visible availability state used in dashboard fingerprints."""
        return {
            "🟢": "available",
            "🟡": "requested",
            "⚪": "not_requested",
        }[cls.status_icon(movie)]
