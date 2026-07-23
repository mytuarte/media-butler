import requests

from models.delete_result import DeleteResult
from services.log_service import logger
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
                refresh=True,
            )

            if request is not None:
                if request.media_id is None:
                    logger.warning(
                        "Overseerr media ID is missing for %s; media data cannot be cleared.",
                        media.title,
                    )
                else:
                    try:
                        services.overseerr.clear_media_data(
                            request.media_id,
                        )
                        logger.info(
                            "Overseerr media data cleared for %s.",
                            media.title,
                        )
                    except requests.HTTPError as error:
                        if error.response is None or error.response.status_code != 404:
                            logger.error(
                                "Overseerr media data cleanup failed for %s: %s",
                                media.title,
                                error,
                            )
                            raise

                        services.overseerr.invalidate_request_cache()
                        logger.info(
                            "Overseerr media data already cleared for %s.",
                            media.title,
                        )

                try:
                    services.overseerr.delete_request(
                        request.id,
                    )
                    result.overseerr_deleted = True
                    logger.info(
                        "Overseerr request deleted for %s.",
                        media.title,
                    )
                except requests.HTTPError as error:
                    if error.response is None or error.response.status_code != 404:
                        logger.error(
                            "Overseerr request deletion failed for %s: %s",
                            media.title,
                            error,
                        )
                        raise

                    services.overseerr.invalidate_request_cache()
                    result.overseerr_deleted = True
                    logger.info(
                        "Overseerr request already deleted for %s.",
                        media.title,
                    )

            return result

        if media.media_type == "series":
            raise NotImplementedError(
                "Series deletion has not been implemented yet."
            )

        raise ValueError(
            f"Unsupported media type: {media.media_type}"
        )
