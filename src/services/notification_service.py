from models.notification import MovieNotification
from services.discord_service import DiscordService


class NotificationService:
    def __init__(self, discord_service: DiscordService):
        self.discord_service = discord_service

    async def send_test_notification(self):
        movie = MovieNotification(
            title="The Matrix",
            year=1999,
            requester="Mike",
            quality="4K BluRay",
        )

        await self.discord_service.send_movie_notification(movie)