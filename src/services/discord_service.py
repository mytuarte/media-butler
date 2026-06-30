import discord

from config import Config
from models.notification import MovieNotification


class DiscordService:
    def __init__(self):
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)

    async def send_movie_notification(
        self,
        channel: discord.TextChannel,
        movie: MovieNotification,
    ):
        embed = discord.Embed(
            title=f"🎬 {movie.title} ({movie.year})",
            description=f"**{movie.status}**",
            color=0x2ECC71,
        )

        embed.add_field(
            name="👤 Requested By",
            value=movie.requester,
            inline=True,
        )

        embed.add_field(
            name="🎞 Quality",
            value=movie.quality,
            inline=True,
        )

        embed.set_footer(text="Media Butler")

        await channel.send(embed=embed)