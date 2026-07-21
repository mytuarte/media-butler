from dataclasses import dataclass
from datetime import datetime


@dataclass
class HealthIssue:
    title: str
    issue_type: str
    details: str

    created_at: datetime

    severity: str = "warning"

    @property
    def alert_key(self) -> str:
        issue_type = " ".join(self.issue_type.split()).casefold()
        title = " ".join(self.title.split()).casefold()

        return f"{issue_type}:{title}"
