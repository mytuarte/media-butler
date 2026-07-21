from datetime import datetime, timedelta

from models.recent_download import RecentDownload
from services.overseerr_service import OverseerrService
from services.radarr_service import RadarrService
from services.recent_episode_grouper import RecentEpisodeGrouper
from services.sonarr_service import SonarrService


class RecentDownloadService:
    def __init__(self):
        self.radarr = RadarrService()
        self.sonarr = SonarrService()
        self.overseerr = OverseerrService()

    def get_recent_downloads(
        self,
        days: int = 14,
    ) -> list[RecentDownload]:
        """
        Returns recently downloaded media currently in the library.
        """

        cutoff = datetime.now() - timedelta(days=days)

        downloads: list[RecentDownload] = []

        downloads.extend(self._get_recent_movies(cutoff))

        downloads.extend(self._get_recent_episodes(cutoff))

        downloads.sort(
            key=lambda item: item.downloaded_date,
            reverse=True,
        )

        return downloads

    def _get_recent_movies(
        self,
        cutoff: datetime,
    ) -> list[RecentDownload]:
        downloads: list[RecentDownload] = []

        for movie in self.radarr.get_movies():
            if not movie.get("hasFile"):
                continue

            movie_file = movie.get("movieFile")

            if movie_file is None:
                continue

            downloaded_date = datetime.fromisoformat(
                movie_file["dateAdded"].replace(
                    "Z",
                    "+00:00",
                )
            ).replace(tzinfo=None)

            if downloaded_date < cutoff:
                continue

            request = self.overseerr.get_request(movie.get("tmdbId"))

            requester = request.requester if request else None

            downloads.append(
                RecentDownload(
                    title=f'{movie["title"]} ({movie["year"]})',
                    media_type="movie",
                    downloaded_date=downloaded_date,
                    size_bytes=movie_file.get(
                        "size",
                        0,
                    ),
                    quality=movie_file.get(
                        "quality",
                        {},
                    )
                    .get(
                        "quality",
                        {},
                    )
                    .get(
                        "name",
                        "Unknown",
                    ),
                    requester=requester,
                )
            )

        return downloads

    def _get_recent_episodes(
        self,
        cutoff: datetime,
    ) -> list[RecentDownload]:
        downloads: list[RecentDownload] = []

        series_lookup = {series["id"]: series for series in self.sonarr.get_series()}

        request_lookup = self.overseerr.get_request_lookup()

        episode_lookup_cache: dict[int, dict[int, dict]] = {}

        for file in self.sonarr.get_all_episode_files():
            downloaded_date = datetime.fromisoformat(
                file["dateAdded"].replace(
                    "Z",
                    "+00:00",
                )
            ).replace(tzinfo=None)

            if downloaded_date < cutoff:
                continue

            series = series_lookup.get(
                file["seriesId"],
            )

            if series is None:
                continue

            series_id = series["id"]

            if series_id not in episode_lookup_cache:
                episode_lookup_cache[series_id] = {
                    episode["episodeFileId"]: episode
                    for episode in self.sonarr.get_episodes(series_id)
                    if episode.get("episodeFileId")
                }

            episode = episode_lookup_cache[series_id].get(
                file["id"],
            )

            if episode is None:
                continue

            request = request_lookup.get(
                series.get("tmdbId"),
            )

            requester = request.requester if request else None

            downloads.append(
                RecentDownload(
                    title=series["title"],
                    media_type="episode",
                    downloaded_date=downloaded_date,
                    size_bytes=file.get(
                        "size",
                        0,
                    ),
                    quality=file.get(
                        "quality",
                        {},
                    )
                    .get(
                        "quality",
                        {},
                    )
                    .get(
                        "name",
                        "Unknown",
                    ),
                    requester=requester,
                    season_number=episode["seasonNumber"],
                    episode_number=episode["episodeNumber"],
                    episode_title=episode["title"],
                    episodes=[
                        (
                            episode["seasonNumber"],
                            episode["episodeNumber"],
                            episode["title"],
                        )
                    ],
                )
            )

        return RecentEpisodeGrouper.group(downloads)
