import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from config import Config
from models.discovery.discovery_item import DiscoveryItem
from models.upcoming_movies_state import UpcomingMoviesState
from services.discovery.discovery_service import DiscoveryService
from services.log_service import logger
from services.registry import services
from views.media_list_view import MediaListView


class UpcomingMovieWatchlistService:
    """The existing release-focused dashboard, kept separate from popularity."""

    STATE_FILE = Path("data/upcoming_movies.json")
    LEGACY_STATE_FILE = Path("data/trending_movies.json")
    DASHBOARD_TITLE = "🎬 Upcoming Movie Watchlist"

    def __init__(self):
        self._migrate_legacy_state()
        self.discovery = DiscoveryService()
        self.state = self._load_state()
        self._task = None
        self.running = False

    def _migrate_legacy_state(self):
        """Keep the pre-split watchlist message attached to its own dashboard."""
        if self.STATE_FILE.exists() or not self.LEGACY_STATE_FILE.exists():
            return
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.LEGACY_STATE_FILE.replace(self.STATE_FILE)
        except OSError as error:
            logger.warning("Failed to migrate upcoming movies state: %s", error)

    def start(self):
        if self.running or Config.DISCORD_TRENDING_MOVIES_CHANNEL_ID is None:
            return False
        if Config.TRENDING_MOVIES_INTERVAL_HOURS <= 0:
            logger.error("TRENDING_MOVIES_INTERVAL_HOURS must be greater than zero.")
            return False
        self.running = True
        self._task = asyncio.create_task(self._run_loop())
        return True

    async def _run_loop(self):
        while self.running:
            try:
                await self.run_cycle()
            except Exception:
                logger.exception("Upcoming movie watchlist scheduler cycle failed.")
            await asyncio.sleep(Config.TRENDING_MOVIES_INTERVAL_HOURS * 60 * 60)

    async def run_cycle(self):
        if services.discord is None:
            return
        movies = await asyncio.to_thread(self.discovery.get_trending_movies)
        fingerprint = self._fingerprint(movies)
        if self.state is not None:
            exists = await services.discord.upcoming_movies_message_exists(
                self.state.message_id
            )
            if exists is None:
                return
            if not exists:
                message = await services.discord.send_upcoming_movies(
                    self._embed(movies)
                )
                self._save_state(fingerprint, message.id)
                return
            if self.state.fingerprint == fingerprint:
                return
        if self.state is None:
            message = await services.discord.send_upcoming_movies(self._embed(movies))
            self._save_state(fingerprint, message.id)
            return
        updated = await services.discord.update_upcoming_movies(
            self.state.message_id,
            self._embed(movies),
        )
        if updated is True:
            self._save_state(fingerprint, self.state.message_id)
        elif updated is False:
            message = await services.discord.send_upcoming_movies(self._embed(movies))
            self._save_state(fingerprint, message.id)

    def _embed(self, movies):
        return MediaListView.build(self.DASHBOARD_TITLE, movies)

    @staticmethod
    def _fingerprint(movies: list[DiscoveryItem]) -> str:
        content = [
            {
                "tmdb_id": movie.tmdb_id,
                "title": movie.title,
                "monitoring_state": movie.monitoring_state.name,
                "status_detail": movie.status_detail,
            }
            for movie in movies
        ]
        serialized = json.dumps(
            content,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(serialized.encode()).hexdigest()

    def _load_state(self) -> UpcomingMoviesState | None:
        if not self.STATE_FILE.exists():
            return None
        try:
            return UpcomingMoviesState.from_dict(
                json.loads(self.STATE_FILE.read_text())
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            logger.warning("Failed to load upcoming movies state: %s", error)
            return None

    def _save_state(self, fingerprint: str, message_id: int):
        self.state = UpcomingMoviesState(
            fingerprint,
            message_id,
            datetime.now(timezone.utc).isoformat(),
        )
        temporary_file = self.STATE_FILE.with_suffix(".tmp")
        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary_file.write_text(json.dumps(self.state.to_dict(), indent=4))
            temporary_file.replace(self.STATE_FILE)
        except OSError as error:
            logger.error("Failed to save upcoming movies state: %s", error)
