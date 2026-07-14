import discord


class TrendingView:
    @staticmethod
    def build(movies):
        embed = discord.Embed(
            title="🔥 Trending Movies This Week",
            color=discord.Color.orange(),
        )

        if not movies:
            embed.description = "No trending movies found."

            embed.set_footer(text="Media Butler")

            return embed

        lines = []

        for index, movie in enumerate(
            movies,
            start=1,
        ):
            lines.append(f"`{index:>2}.` {movie.title}")

        embed.description = "\n".join(lines)

        embed.set_footer(text="Media Butler")

        return embed
