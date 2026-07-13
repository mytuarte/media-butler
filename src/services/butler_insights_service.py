from datetime import date

from models.butler_insight import ButlerInsight
from models.media_result import MediaResult


class ButlerInsightsService:
    @staticmethod
    def generate(result: MediaResult) -> list[ButlerInsight]:
        insights: list[ButlerInsight] = []

        # Released movie with no download
        if (
            result.media_type == "movie"
            and not result.has_file
            and result.release_date
            and result.release_date < date.today()
        ):
            days = (date.today() - result.release_date).days

            insights.append(
                ButlerInsight(
                    icon="⚠️",
                    message=(
                        f"Released {days} days ago, "
                        "but no download has started."
                    ),
                    priority=100,
                )
            )

        return sorted(
            insights,
            key=lambda insight: insight.priority,
            reverse=True,
        )