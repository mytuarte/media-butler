from dataclasses import dataclass

import discord


@dataclass(frozen=True)
class PipelineState:
    id: str
    title: str
    description: str
    emoji: str
    color: discord.Color

    @property
    def display(self) -> str:
        return f"{self.emoji} {self.title}"


READY = PipelineState(
    id="ready",
    title="Ready to Watch",
    description="Media is available in Plex.",
    emoji="🟢",
    color=discord.Color.green(),
)

DOWNLOADING = PipelineState(
    id="downloading",
    title="Downloading",
    description="Episodes are still being acquired.",
    emoji="🟡",
    color=discord.Color.orange(),
)

REQUESTED = PipelineState(
    id="requested",
    title="Requested",
    description="Waiting for Radarr/Sonarr.",
    emoji="🔵",
    color=discord.Color.blue(),
)

AWAITING_RELEASE = PipelineState(
    id="awaiting_release",
    title="Awaiting Release",
    description="Waiting for the official release.",
    emoji="📅",
    color=discord.Color.gold(),
)

WANTED = PipelineState(
    id="wanted",
    title="Wanted",
    description="Monitored but not requested.",
    emoji="🟠",
    color=discord.Color.orange(),
)

NOT_MONITORED = PipelineState(
    id="not_monitored",
    title="Not Monitored",
    description="Media is not monitored.",
    emoji="⚪",
    color=discord.Color.light_grey(),
)