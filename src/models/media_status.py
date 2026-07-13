from dataclasses import dataclass

import discord


@dataclass(frozen=True)
class MediaStatus:
    text: str
    emoji: str
    color: discord.Color

    @property
    def display(self) -> str:
        return f"{self.emoji} {self.text}"

    @staticmethod
    def from_result(result) -> "MediaStatus":
        if result.has_file:
            return MediaStatus(
                text="Downloaded",
                emoji="✅",
                color=discord.Color.green(),
            )

        if result.monitored and not result.is_available:
            return MediaStatus(
                text="Awaiting Release",
                emoji="📅",
                color=discord.Color.gold(),
            )

        if result.monitored:
            return MediaStatus(
                text="Wanted",
                emoji="⏳",
                color=discord.Color.orange(),
            )

        return MediaStatus(
            text="Not Monitored",
            emoji="❌",
            color=discord.Color.red(),
        )