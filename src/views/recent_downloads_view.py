import discord

from models.recent_download import RecentDownload


class RecentDownloadsView:
    @staticmethod
    def build(
        downloads: list[RecentDownload],
        days: int,
    ) -> discord.Embed:
        embed = discord.Embed(
            title=f"🆕 Recent Downloads ({days} Days)",
            color=0x2ECC71,
        )

        if not downloads:
            embed.description = "No recent downloads."
            return embed

        movie_count = sum(1 for download in downloads if download.media_type == "movie")

        episode_count = sum(
            len(download.episodes)
            for download in downloads
            if download.media_type == "episode"
        )

        total_size = sum(download.size_bytes for download in downloads)

        total_gb = total_size / (1024**3)

        embed.add_field(
            name="📊 Summary",
            value=(
                f"🎬 Movies: {movie_count}\n"
                f"📺 Episodes: {episode_count}\n"
                f"💾 Total Size: {total_gb:.1f} GB"
            ),
            inline=False,
        )

        # Discord embeds support a maximum of 25 fields.
        for download in downloads[:24]:
            size_gb = download.size_bytes / (1024**3)

            lines = []

            if download.media_type == "episode":
                episodes = sorted(download.episodes)

                if len(episodes) == 1:
                    season, episode, title = episodes[0]

                    text = f"📺 S{season:02d}E{episode:02d}"

                    if title:
                        text += f" • {title}"

                    lines.append(text)

                else:
                    lines.append(f"📺 {len(episodes)} Episodes")

                    seasons: dict[int, list[int]] = {}

                    for season, episode, _ in episodes:
                        seasons.setdefault(
                            season,
                            [],
                        ).append(episode)

                    for season in sorted(seasons):
                        episode_numbers = sorted(
                            seasons[season],
                        )

                        if episode_numbers == list(
                            range(
                                min(episode_numbers),
                                max(episode_numbers) + 1,
                            )
                        ):
                            lines.append(
                                f"S{season:02d}: "
                                f"E{min(episode_numbers):02d}"
                                f"-"
                                f"E{max(episode_numbers):02d}"
                            )
                        else:
                            lines.append(
                                f"S{season:02d}: "
                                + ", ".join(
                                    f"E{episode:02d}" for episode in episode_numbers
                                )
                            )

            if download.requester:
                lines.append(f"👤 {download.requester}")

            lines.append(f"📅 {download.downloaded_date:%b %d, %Y}")

            lines.append(f"💾 {size_gb:.1f} GB")

            lines.append(f"🎞 {download.quality}")

            embed.add_field(
                name=download.title,
                value="\n".join(lines),
                inline=False,
            )

        if len(downloads) > 24:
            embed.set_footer(
                text=(
                    f"Showing first 24 of "
                    f"{len(downloads)} recent downloads • "
                    "Media Butler"
                )
            )
        else:
            embed.set_footer(text="Media Butler")

        return embed
