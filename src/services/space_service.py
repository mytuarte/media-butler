import shutil

from config import Config
from models.space_item import SpaceItem
from models.space_result import SpaceResult
from services.registry import services


class SpaceService:
    def get_summary(self):
        total, used, free = shutil.disk_usage(
            Config.MEDIA_ROOT
        )

        movies = services.radarr.get_movies()
        series = services.sonarr.get_series()

        movie_bytes = sum(
            movie.get("movieFile", {}).get("size", 0)
            for movie in movies
            if movie.get("hasFile")
        )

        series_bytes = sum(
            series_item.get("statistics", {}).get(
                "sizeOnDisk",
                0,
            )
            for series_item in series
        )

        largest_movies = sorted(
            [
                SpaceItem(
                    title=movie["title"],
                    size_bytes=movie["movieFile"]["size"],
                )
                for movie in movies
                if movie.get("hasFile")
                and movie.get("movieFile")
            ],
            key=lambda movie: movie.size_bytes,
            reverse=True,
        )[:20]

        return SpaceResult(
            total_bytes=total,
            used_bytes=used,
            free_bytes=free,

            movie_count=len(movies),
            series_count=len(series),

            movie_bytes=movie_bytes,
            series_bytes=series_bytes,

            largest_movies=largest_movies,
        )