import discord

from services.media_service import MediaService


class FindCommand:
    """
    Searches the media library.
    """

    COMMAND = "find"
    DESCRIPTION = "Searches Radarr and Sonarr for matching media."

    def __init__(self):
        self.media = MediaService()

    async def execute(self, message):
        parts = message.content.split(maxsplit=1)

        if len(parts) < 2:
            await message.channel.send(
                "Usage: `!find <title>`"
            )
            return

        query = parts[1].strip()

        results = self.media.search(query)

        if not results:
            await message.channel.send(
                f'No media found matching "{query}".'
            )
            return

        # For now, display the first result.
        # Later we'll handle multiple results with buttons.
        result = results[0]

        status = "Downloaded" if result.has_file else "Missing"
        monitored = "Yes" if result.monitored else "No"

        embed = discord.Embed(
            title=f"🎬 {result.title} ({result.year})",
            color=0x2ECC71 if result.has_file else 0xE74C3C,
        )

        embed.add_field(
            name="Status",
            value=status,
            inline=False,
        )

        embed.add_field(
            name="Quality",
            value=result.quality,
            inline=False,
        )

        embed.add_field(
            name="Monitored",
            value=monitored,
            inline=False,
        )

        embed.set_footer(text="Media Butler")

        await message.channel.send(embed=embed)