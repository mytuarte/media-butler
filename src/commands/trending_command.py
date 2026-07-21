from models.command_channel import CommandChannel
from services.discovery.discovery_service import (
    DiscoveryService,
)
from views.media_list_view import MediaListView


class TrendingCommand:
    COMMAND = "trending"

    DESCRIPTION = "Shows the current trending movies from TMDb."

    CHANNELS = {
        CommandChannel.ADMIN,
        CommandChannel.GENERAL,
    }

    def __init__(self):
        self.discovery = DiscoveryService()

    async def execute(self, message):
        movies = self.discovery.get_trending_movies()

        embed = MediaListView.build(
            "🔥 Trending Movies This Week",
            movies,
        )

        await message.channel.send(embed=embed)
