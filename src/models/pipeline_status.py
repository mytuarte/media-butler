from dataclasses import dataclass

import discord


@dataclass(frozen=True)
class PipelineStatus:
    text: str
    emoji: str
    color: discord.Color

    @property
    def display(self) -> str:
        return f"{self.emoji} {self.text}"