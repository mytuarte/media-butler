from models.command_channel import CommandChannel
from services.discovery.tmdb_service import TmdbService


class TrendingCommand:
    """
    Displays trending movies.
    """

    COMMAND = "trending"
    DESCRIPTION = "Displays trending movies."

    CHANNELS = {
        CommandChannel.ADMIN,
        CommandChannel.GENERAL,
    }

    def __init__(self):
        self.tmdb = TmdbService()

    async def execute(self, message):
        data = self.tmdb.get_trending_movies()

        first = data["results"][0]

        await message.channel.send(
            f"#{1} {first['title']} ({first['release_date']})"
        )