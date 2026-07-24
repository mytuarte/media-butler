import discord

from models.series_completion_notification import SeriesCompletionNotification


class SeriesCompletionNotificationView:
    @staticmethod
    def build(notification: SeriesCompletionNotification) -> discord.Embed:
        title = f"📺 {notification.title}"
        if notification.year is not None:
            title += f" ({notification.year})"
        embed = discord.Embed(
            title=title,
            description=f"**{notification.status}**",
            color=0x2ECC71,
        )
        embed.add_field(
            name="Episodes",
            value=f"{notification.downloaded_episodes} / {notification.released_episodes}",
            inline=True,
        )
        valid_discord_id = (
            isinstance(notification.requester_discord_id, int)
            and not isinstance(notification.requester_discord_id, bool)
            and notification.requester_discord_id > 0
        )
        requester = notification.requester_name or (
            "Discord user" if valid_discord_id else "Unknown"
        )
        embed.add_field(name="Requested By", value=requester, inline=True)
        embed.set_footer(text="Media Butler")
        return embed
