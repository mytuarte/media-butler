import discord

from config import Config
from models.notification import MovieNotification


class DiscordService:
    def __init__(self):
        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        
        @self.client.event
        async def on_ready():
            print(f"Discord connected as {self.client.user}")

    async def start(self):
        print(f"Discord token loaded: {Config.DISCORD_TOKEN is not None}")
        await self.client.start(Config.DISCORD_TOKEN)

    async def send_movie_notification(
        self,
        movie: MovieNotification,
    ):
        channel = self.client.get_channel(Config.DISCORD_CHANNEL_ID)

        if channel is None:
            raise RuntimeError("Discord channel not found.")

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