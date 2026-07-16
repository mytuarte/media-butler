from dataclasses import dataclass
from datetime import datetime


@dataclass
class HealthIssue:
    title: str
    issue_type: str
    details: str

    created_at: datetime

    severity: str = "warning"
