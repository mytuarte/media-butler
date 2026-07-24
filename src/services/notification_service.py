from config import Config
from models.notification import MovieNotification
from models.series_completion_notification import SeriesCompletionNotification
from services.discord_service import DiscordService


class NotificationService:
    def __init__(self, discord_service: DiscordService):
        self.discord_service = discord_service

    async def send_movie_notification(self, movie: MovieNotification):
        await self.discord_service.send_movie_notification(movie)

    async def send_series_completion_notification(
        self, notification: SeriesCompletionNotification
    ):
        await self.discord_service.send_series_completion_notification(notification)

    async def send_test_notification(self):
        movie = MovieNotification(
            title="The Matrix",
            year=1999,
            requester=Config.USERS["michaelytuarte"],
            quality="4K BluRay",
        )

        await self.send_movie_notification(movie)