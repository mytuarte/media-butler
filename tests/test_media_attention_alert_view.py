import unittest
from datetime import datetime, timezone

from models.media_attention import (
    EpisodeProgress,
    MediaAttentionAlert,
    MediaAttentionMediaType,
    PipelineSnapshot,
    PipelineStage,
)
from views.media_attention_alert_view import MediaAttentionAlertView


def tv_snapshot(progress=None, stage=PipelineStage.WAITING_FOR_SONARR):
    return PipelineSnapshot(
        media_key="tv:tmdb:1", media_type=MediaAttentionMediaType.TV,
        tmdb_id=1, request_id=1, title="Example", stage=stage,
        stage_detail="Waiting for Sonarr.", arr_evidence={"present": False},
        episode_progress=progress,
    )


def tv_alert(stage=PipelineStage.WAITING_FOR_SONARR):
    return MediaAttentionAlert("tv:tmdb:1", MediaAttentionMediaType.TV, 1, 1,
        "Example", stage, "active", datetime.now(timezone.utc))


class MediaAttentionAlertViewTests(unittest.TestCase):
    def test_waiting_for_sonarr_has_safe_unavailable_episode_progress(self):
        embed = MediaAttentionAlertView.build(tv_alert(), tv_snapshot(), 120)
        fields = {field.name: field.value for field in embed.fields}
        self.assertEqual(fields["📺 Series"], "Example")
        self.assertEqual(fields["Episode Progress"], "Unavailable until the series reaches Sonarr.")
        self.assertIn("Sonarr: No series", fields["Details"])
        self.assertNotIn("SAB", str(embed.to_dict()))

    def test_normal_tv_progress_and_resolved_output_are_neutral(self):
        progress = EpisodeProgress(("S01E01", "S01E02"), ("S01E01",))
        snapshot = tv_snapshot(progress, PipelineStage.DOWNLOADING)
        snapshot = PipelineSnapshot(**{key: getattr(snapshot, key) for key in (
            "media_key", "media_type", "tmdb_id", "request_id", "title", "stage", "stage_detail", "arr_evidence", "sab_evidence", "plex_evidence", "episode_progress")})
        embed = MediaAttentionAlertView.build(tv_alert(PipelineStage.DOWNLOADING), snapshot, 20)
        self.assertIn("Released Episodes: 2", str(embed.to_dict()))
        resolved = MediaAttentionAlertView.build_resolved(tv_alert(), tv_snapshot())
        self.assertNotIn("SAB", str(resolved.to_dict()))
