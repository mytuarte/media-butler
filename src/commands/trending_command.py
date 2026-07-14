from models.command_channel import CommandChannel
from services.discovery.discovery_service import DiscoveryService

from views.trending_view import TrendingView


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
        self.discovery = DiscoveryService()

    async def execute(self, message):
        movies = self.discovery.get_trending_movies()

        if not movies:
            await message.channel.send("No trending movies found.")
            return

        embed = TrendingView.build(movies)

        await message.channel.send(
            embed=embed,
        )
