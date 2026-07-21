from models.command_channel import CommandChannel
from services.discovery.discovery_service import (
    DiscoveryService,
)
from views.media_list_view import MediaListView


class TrendingTvCommand:
    COMMAND = "trendingtv"

    DESCRIPTION = "Shows the current trending TV shows from TMDb."

    CHANNELS = {
        CommandChannel.ADMIN,
        CommandChannel.GENERAL,
    }

    def __init__(self):
        self.discovery = DiscoveryService()

    async def execute(self, message):
        shows = self.discovery.get_trending_tv()

        embed = MediaListView.build(
            "📺 Trending TV This Week",
            shows,
        )

        await message.channel.send(embed=embed)
