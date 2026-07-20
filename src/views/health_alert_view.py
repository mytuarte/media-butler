import discord

from models.health_issue import HealthIssue
from views.base_view import BaseView


class HealthAlertView(BaseView):
    @staticmethod
    def build(
        issue: HealthIssue,
    ) -> discord.Embed:
        embed = discord.Embed(
            title="🚨 Media Butler Health Alert",
            color=0xE74C3C,
        )

        embed.add_field(
            name="Issue",
            value=issue.title,
            inline=False,
        )

        embed.add_field(
            name="Type",
            value=issue.issue_type,
            inline=True,
        )

        embed.add_field(
            name="Severity",
            value=issue.severity.title(),
            inline=True,
        )

        embed.add_field(
            name="Details",
            value=issue.details,
            inline=False,
        )

        embed.set_footer(text="Media Butler")

        return embed
