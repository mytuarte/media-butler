from dataclasses import dataclass


@dataclass
class SeasonStatus:
    season_number: int
    downloaded_episodes: int
    total_episodes: int

    @property
    def is_complete(self) -> bool:
        return (
            self.total_episodes > 0
            and self.downloaded_episodes == self.total_episodes
        )

    @property
    def is_empty(self) -> bool:
        return self.downloaded_episodes == 0

    @property
    def is_partial(self) -> bool:
        return (
            self.downloaded_episodes > 0
            and not self.is_complete
        )

    @property
    def is_released(self) -> bool:
        return self.total_episodes > 0

    @property
    def display(self) -> str:
        if self.is_complete:
            return f"✅ S{self.season_number}"

        if self.is_partial:
            return (
                f"🟡 S{self.season_number} "
                f"({self.downloaded_episodes}/{self.total_episodes})"
            )

        return f"❌ S{self.season_number}"