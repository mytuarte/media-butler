from models.command_channel import CommandChannel
from services.recent_download_service import (
    RecentDownloadService,
)
from views.recent_downloads_view import (
    RecentDownloadsView,
)


class RecentCommand:
    """
    Shows recently downloaded media.
    """

    COMMAND = "recent"

    DESCRIPTION = "Shows media downloaded during the last 14 days."

    CHANNELS = {
        CommandChannel.ADMIN,
    }

    def __init__(self):
        self.recent = RecentDownloadService()

    async def execute(self, message):
        parts = message.content.split(maxsplit=1)

        days = 14

        if len(parts) == 2:
            try:
                days = int(parts[1])
            except ValueError:
                await message.channel.send("Usage: `!recent [days]`")
                return

        downloads = self.recent.get_recent_downloads(days)

        embed = RecentDownloadsView.build(
            downloads,
            days,
        )

        await message.channel.send(
            embed=embed,
        )
