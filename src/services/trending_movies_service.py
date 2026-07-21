import asyncio
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from config import Config
from models.discovery.discovery_item import DiscoveryItem
from models.trending_movies_state import TrendingMoviesState
from services.discovery.discovery_service import DiscoveryService
from services.log_service import logger
from services.registry import services
from views.trending_movies_view import TrendingMoviesView


class TrendingMoviesService:
    STATE_FILE = Path("data/trending_movies.json")
    DASHBOARD_TITLE = TrendingMoviesView.TITLE

    def __init__(self):
        self.discovery = DiscoveryService()
        self.state = self._load_state()
        self._task = None
        self.running = False

    def start(self):
        if self.running:
            return False

        if Config.DISCORD_TRENDING_MOVIES_CHANNEL_ID is None:
            logger.info(
                "Trending movies scheduler is disabled: "
                "DISCORD_TRENDING_MOVIES_CHANNEL_ID is not configured."
            )
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
                logger.exception("Trending movies scheduler cycle failed.")

            await asyncio.sleep(Config.TRENDING_MOVIES_INTERVAL_HOURS * 60 * 60)

    async def run_cycle(self):
        if services.discord is None:
            logger.warning("Trending movies scheduler cannot send without Discord.")
            return

        movies = await asyncio.to_thread(self.discovery.get_trending_movies)
        movies = self._released_movies(movies)
        fingerprint = self._fingerprint(movies)

        if self.state is not None:
            message_exists = await services.discord.trending_movies_message_exists(
                self.state.message_id
            )

            if message_exists is None:
                return

            if not message_exists:
                embed = TrendingMoviesView.build(movies)
                message = await services.discord.send_trending_movies(embed)
                self._save_state(fingerprint, message.id)
                return

            if message_exists and self.state.fingerprint == fingerprint:
                return

        embed = TrendingMoviesView.build(movies)

        if self.state is None:
            message = await services.discord.send_trending_movies(embed)
            self._save_state(fingerprint, message.id)
            return

        updated = await services.discord.update_trending_movies(
            self.state.message_id,
            embed,
        )

        if updated is True:
            self._save_state(fingerprint, self.state.message_id)
            return

        if updated is False:
            message = await services.discord.send_trending_movies(embed)
            self._save_state(fingerprint, message.id)

    @staticmethod
    def _fingerprint(movies: list[DiscoveryItem]) -> str:
        content = [
            {
                "tmdb_id": movie.tmdb_id,
                "title": movie.title,
                "availability": TrendingMoviesView.status(movie),
            }
            for movie in movies
        ]
        serialized = json.dumps(
            content,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        return hashlib.sha256(serialized.encode()).hexdigest()

    @staticmethod
    def _released_movies(movies: list[DiscoveryItem]) -> list[DiscoveryItem]:
        """Exclude announced and future movies from the right-now dashboard."""
        released_movies = []

        for movie in movies:
            if movie.release_date is None:
                continue

            try:
                release_date = date.fromisoformat(movie.release_date)
            except ValueError:
                continue

            if release_date <= date.today():
                released_movies.append(movie)

        return released_movies

    def _load_state(self) -> TrendingMoviesState | None:
        if not self.STATE_FILE.exists():
            return None

        try:
            with open(self.STATE_FILE, "r") as file:
                return TrendingMoviesState.from_dict(json.load(file))
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
            logger.warning("Failed to load trending movies state: %s", error)
            return None

    def _save_state(
        self,
        fingerprint: str,
        message_id: int,
    ):
        self.state = TrendingMoviesState(
            fingerprint=fingerprint,
            message_id=message_id,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        temporary_file = self.STATE_FILE.with_suffix(".tmp")

        try:
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            temporary_file.write_text(
                json.dumps(
                    self.state.to_dict(),
                    indent=4,
                )
            )
            temporary_file.replace(self.STATE_FILE)
        except OSError as error:
            logger.error("Failed to save trending movies state: %s", error)
