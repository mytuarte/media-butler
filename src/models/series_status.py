from dataclasses import dataclass

import discord

from models.media_result import MediaResult


@dataclass(frozen=True)
class SeriesStatus:
    text: str
    emoji: str
    color: discord.Color

    @property
    def display(self) -> str:
        return f"{self.emoji} {self.text}"

    @staticmethod
    def from_result(result: MediaResult) -> "SeriesStatus":
        if result.total_episodes == 0:
            return SeriesStatus(
                text="Awaiting First Release",
                emoji="📅",
                color=discord.Color.gold(),
            )

        if result.downloaded_episodes == 0:
            return SeriesStatus(
                text="No Episodes Downloaded",
                emoji="❌",
                color=discord.Color.red(),
            )

        if result.downloaded_episodes < result.total_episodes:
            return SeriesStatus(
                text="Download In Progress",
                emoji="🟡",
                color=discord.Color.orange(),
            )

        return SeriesStatus(
            text="All Released Episodes Downloaded",
            emoji="✅",
            color=discord.Color.green(),
        )