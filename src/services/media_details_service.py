from models.media_details import MediaDetails
from services.registry import services


class MediaDetailsService:
    def get_details(self, media):
        details = MediaDetails(
            media=media,
        )

        if media.overseerr is not None:
            details.requester = media.overseerr.requester
            details.requested_date = (
                media.overseerr.requested_date
            )

        if media.media_type == "movie":
            movies = services.radarr.get_movies()

            movie = next(
                (
                    m
                    for m in movies
                    if m["id"] == media.id
                ),
                None,
            )

            if movie is not None:
                movie_file = movie.get("movieFile", {})

                details.size_bytes = movie_file.get("size")
                details.path = movie.get("path")
                details.added_date = movie.get("added")

        return details