import discord

from models.discovery.discovery_item import DiscoveryItem


class MediaListView:
    @staticmethod
    def build(
        title: str,
        media: list[DiscoveryItem],
    ):
        embed = discord.Embed(
            title=title,
            color=discord.Color.orange(),
        )

        if not media:
            embed.description = "No media found."
            embed.set_footer(text="🟢 In Library • 🟡 Requested • ⚪ Not Owned")
            return embed

        media = sorted(
            media,
            key=MediaListView._sort_key,
        )

        lines = []

        for item in media:
            icon = MediaListView._status_icon(item)
            lines.append(f"{icon} {item.title}")

        embed.description = "\n".join(lines)

        embed.set_footer(text="🟢 In Library • 🟡 Requested • ⚪ Not Owned")

        return embed

    @staticmethod
    def _status_icon(
        item: DiscoveryItem,
    ) -> str:
        if item.in_library:
            return "🟢"

        if item.requested:
            return "🟡"

        return "⚪"

    @staticmethod
    def _sort_key(
        item: DiscoveryItem,
    ) -> tuple[int]:
        if item.in_library:
            return (0,)

        if item.requested:
            return (1,)

        return (2,)
