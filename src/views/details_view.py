from models.media_result import MediaResult
from views.movie_details_view import MovieDetailsView
from views.series_details_view import SeriesDetailsView


class DetailsView:
    @staticmethod
    def build(result: MediaResult):
        if result.media_type == "movie":
            return MovieDetailsView.build(result)

        if result.media_type == "series":
            return SeriesDetailsView.build(result)

        raise ValueError(
            f"Unsupported media type: {result.media_type}"
        )