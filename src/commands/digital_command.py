from models.command_channel import CommandChannel
from services.discovery.discovery_service import (
    DiscoveryService,
)
from views.media_list_view import MediaListView


class DigitalCommand:
    COMMAND = "digital"

    DESCRIPTION = "Shows recently released digital movies."

    CHANNELS = {
        CommandChannel.ADMIN,
        CommandChannel.GENERAL,
    }

    def __init__(self):
        self.discovery = DiscoveryService()

    async def execute(self, message):
        movies = self.discovery.get_digital_movies()

        embed = MediaListView.build(
            "📀 New Digital Releases",
            movies,
        )

        await message.channel.send(embed=embed)
