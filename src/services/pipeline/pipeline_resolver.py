from datetime import datetime

from models import pipeline_state
from models.media_result import MediaResult
from models.pipeline_result import PipelineResult
from services.pipeline.pipeline_message_builder import (
    PipelineMessageBuilder,
)


class PipelineResolver:
    @staticmethod
    def resolve(result: MediaResult) -> PipelineResult:
        requested_date = None

        if result.requested_date:
            try:
                requested_date = datetime.fromisoformat(
                    result.requested_date.replace("Z", "+00:00")
                ).strftime("%b %d, %Y")
            except ValueError:
                requested_date = result.requested_date

        if result.has_file:
            return PipelineResult(
                state=pipeline_state.READY,
                message=PipelineMessageBuilder.build_ready_message(
                    result
                ),
                requester=result.requester,
                requested_date=requested_date,
            )

        if result.overseerr_media_status == 1:
            return PipelineResult(
                state=pipeline_state.AWAITING_RELEASE,
                message=PipelineMessageBuilder.build_awaiting_release_message(
                    result
                ),
                requester=result.requester,
                requested_date=requested_date,
            )

        if (
            result.media_type == "series"
            and result.downloaded_episodes > 0
        ):
            return PipelineResult(
                state=pipeline_state.DOWNLOADING,
                message=PipelineMessageBuilder.build_downloading_message(
                    result
                ),
                progress=(
                    f"{result.downloaded_episodes} / "
                    f"{result.total_episodes} Episodes"
                ),
                requester=result.requester,
                requested_date=requested_date,
            )

        if result.overseerr_status is not None:
            return PipelineResult(
                state=pipeline_state.REQUESTED,
                message=PipelineMessageBuilder.build_requested_message(
                    result
                ),
                requester=result.requester,
                requested_date=requested_date,
            )

        if result.monitored:
            return PipelineResult(
                state=pipeline_state.WANTED,
                message=PipelineMessageBuilder.build_wanted_message(
                    result
                ),
            )

        return PipelineResult(
            state=pipeline_state.NOT_MONITORED,
            message=PipelineMessageBuilder.build_not_monitored_message(
                result
            ),
        )