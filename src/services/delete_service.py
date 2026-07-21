from models.delete_result import DeleteResult
from services.registry import services


class DeleteService:
    def delete(self, media):
        result = DeleteResult(
            media_title=media.title,
        )

        if media.media_type == "movie":
            services.radarr.delete_movie(media.id)

            result.radarr_deleted = True
            result.files_deleted = True

            request = services.overseerr.get_request(
                media.tmdb_id,
            )

            if request is not None:
                services.overseerr.delete_request(
                    request.id,
                )

                result.overseerr_deleted = True

            return result

        if media.media_type == "series":
            raise NotImplementedError(
                "Series deletion has not been implemented yet."
            )

        raise ValueError(
            f"Unsupported media type: {media.media_type}"
        )