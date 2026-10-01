import asyncio

import discord

from models.discovery.discovery_details import DiscoveryDetails
from models.discovery.discovery_item import DiscoveryItem
from models.discovery.discovery_selection import DiscoverySelection
from models.monitoring_state import MonitoringState
from services.discovery.tmdb_service import TmdbService
from services.log_service import logger
from views.media_list_view import MediaListView
from views.trending_movies_view import TrendingMoviesView
from views.trending_tv_view import TrendingTvView


class DiscoveryDetailsSelect(discord.ui.Select):
    def __init__(
        self,
        selections: list[DiscoverySelection],
        dashboard_key: str,
        tmdb: TmdbService | None = None,
    ):
        options = [
            discord.SelectOption(
                label=self._option_label(selection),
                description=(
                    f"{selection.media_type.upper()} · TMDB {selection.tmdb_id}"
                ),
                value=f"{selection.media_type}:{selection.tmdb_id}",
            )
            for selection in selections[:25]
        ]
        super().__init__(
            custom_id=f"media_butler:discovery_details:{dashboard_key}",
            placeholder="Select a title for details",
            min_values=1,
            max_values=1,
            options=options,
        )
        self.tmdb = tmdb or TmdbService()

    @staticmethod
    def _option_label(selection: DiscoverySelection) -> str:
        label = f"{selection.status_icon} {selection.title}"
        if selection.release_status and selection.status_icon != "🟢":
            label += f" [{selection.release_status}]"
        return label[:100]

    async def callback(self, interaction: discord.Interaction):
        media_type, separator, raw_tmdb_id = self.values[0].partition(":")
        if not separator:
            await interaction.response.send_message(
                "That title could not be identified.",
                ephemeral=True,
            )
            return

        try:
            tmdb_id = int(raw_tmdb_id)
        except ValueError:
            await interaction.response.send_message(
                "That title could not be identified.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            details = await asyncio.to_thread(
                self.tmdb.get_details,
                media_type,
                tmdb_id,
            )
        except Exception:
            logger.exception(
                "Unable to load TMDB details for %s:%s",
                media_type,
                tmdb_id,
            )
            await interaction.followup.send(
                "I couldn't load details for that title right now.",
                ephemeral=True,
            )
            return

        await interaction.followup.send(
            embed=DiscoveryDetailsView.build(details),
            ephemeral=True,
        )


class DiscoveryDetailsView(discord.ui.View):
    """Interactive selection and private details for discovery dashboards."""

    VERSION = 1

    def __init__(
        self,
        selections: list[DiscoverySelection],
        dashboard_key: str,
        tmdb: TmdbService | None = None,
    ):
        super().__init__(timeout=None)
        self.dashboard_key = dashboard_key
        self.add_item(DiscoveryDetailsSelect(selections, dashboard_key, tmdb))

    @property
    def registration_id(self) -> str:
        return f"media_butler:discovery_details:{self.dashboard_key}"

    @classmethod
    def from_items(
        cls,
        items: list[DiscoveryItem],
        dashboard_key: str,
    ) -> "DiscoveryDetailsView | None":
        selections = cls.selections_from_items(items, dashboard_key)
        return cls(selections, dashboard_key) if selections else None

    @classmethod
    def from_selections(
        cls,
        selections: list[DiscoverySelection],
        dashboard_key: str,
    ) -> "DiscoveryDetailsView | None":
        return cls(selections, dashboard_key) if selections else None

    @classmethod
    def selections_from_items(
        cls,
        items: list[DiscoveryItem],
        dashboard_key: str,
    ) -> list[DiscoverySelection]:
        selections = []
        for item in items[:25]:
            selections.append(
                DiscoverySelection(
                    title=item.title,
                    media_type=item.media_type,
                    tmdb_id=item.tmdb_id,
                    status_icon=cls._status_icon(item, dashboard_key),
                    release_status=MediaListView._release_status(item),
                )
            )
        return selections

    @classmethod
    def selection_data(
        cls,
        items: list[DiscoveryItem],
        dashboard_key: str,
    ) -> list[dict]:
        return [
            selection.to_dict()
            for selection in cls.selections_from_items(items, dashboard_key)
        ]

    @staticmethod
    def _status_icon(item: DiscoveryItem, dashboard_key: str) -> str:
        if dashboard_key == "trending_movies":
            return TrendingMoviesView.status_icon(item)
        if dashboard_key == "trending_tv":
            return TrendingTvView.status_icon(item)

        if item.monitoring_state == MonitoringState.AVAILABLE:
            return "🟢"
        if item.monitoring_state == MonitoringState.DOWNLOADING:
            return "⬇️"
        if item.monitoring_state == MonitoringState.COMING_SOON or item.requester:
            return "🟡"
        return "⚪"

    @staticmethod
    def _truncate(value: str, maximum: int) -> str:
        if len(value) <= maximum:
            return value
        return f"{value[: maximum - 1].rstrip()}…"

    @classmethod
    def build(cls, details: DiscoveryDetails) -> discord.Embed:
        is_movie = details.media_type == "movie"
        icon = "🎬" if is_movie else "📺"
        color = discord.Color.orange() if is_movie else discord.Color.blue()
        embed = discord.Embed(
            title=f"{icon} {details.title}",
            description=cls._truncate(
                details.overview or "No synopsis is available for this title.",
                4000,
            ),
            color=color,
        )

        if details.poster_url:
            embed.set_thumbnail(url=details.poster_url)

        if (
            details.vote_average is not None
            and details.vote_count is not None
            and details.vote_count > 0
        ):
            rating = (
                f"{details.vote_average:.1f}/10 "
                f"({details.vote_count:,} votes)"
            )
        else:
            rating = "No viewer rating listed."

        embed.add_field(name="⭐ Viewer rating", value=rating, inline=True)

        streaming = (
            "\n".join(f"• {provider}" for provider in details.streaming_providers)
            if details.streaming_providers
            else "No subscription streaming service listed in the US."
        )
        embed.add_field(name="📺 Streaming", value=streaming, inline=False)

        if details.release_date:
            embed.add_field(
                name="📅 Release date",
                value=details.release_date,
                inline=True,
            )

        embed.set_footer(text="TMDB · US streaming availability")
        return embed
