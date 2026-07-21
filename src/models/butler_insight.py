from dataclasses import dataclass


@dataclass(slots=True)
class ButlerInsight:
    icon: str
    message: str
    priority: int = 0