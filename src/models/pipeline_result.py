from dataclasses import dataclass

from models.pipeline_state import PipelineState


@dataclass(frozen=True)
class PipelineResult:
    state: PipelineState

    message: str | None = None
    next_action: str | None = None

    requester: str | None = None
    requested_date: str | None = None

    progress: str | None = None

    warning: str | None = None