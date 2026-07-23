import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from itertools import chain

from models.media_attention import PipelineStage
from services.media_attention_service import MediaAttentionService


class TvRobustnessTests(unittest.TestCase):
    def test_queue_state_classes_and_representative_status(self):
        active = ("downloading", "queued", "paused", "warning")
        importing = ("completed", "importPending", "importing", "awaitingImport")
        failures = ("failed", "importFailed", "downloadFailed", "ignored", "removed", "unknown", None)
        cases = chain(((value, PipelineStage.DOWNLOADING) for value in active), ((value, PipelineStage.IMPORT_PENDING) for value in importing), ((value, PipelineStage.SONARR_SEARCHING) for value in failures))
        for value, expected in cases:
            with self.subTest(value=value):
                evidence = MediaAttentionService._series_queue_evidence(90, [{"seriesId": "90", "status": value}])
                self.assertEqual(MediaAttentionService._resolve_tv_stage({"id": 90}, SimpleNamespace(caught_up=False), evidence)[0], expected)
        evidence = MediaAttentionService._series_queue_evidence(90, [{"seriesId": 90, "status": "failed", "trackedDownloadState": "downloading", "downloadId": "z", "progress": 5}, {"seriesId": 90, "status": "completed", "downloadId": "a", "progress": 4}])
        self.assertEqual(evidence["status"], "downloading")
        self.assertEqual(evidence["percent"], 5.0)
    def test_queue_normalization_is_order_independent_and_failures_are_not_completed(self):
        records = [
            {"seriesId": 1, "downloadId": "b", "status": "failed", "episodeIds": [3, 3], "size": 100, "sizeleft": 90},
            {"series": {"id": 1}, "downloadId": "a", "trackedDownloadState": "paused", "episodeId": 2, "size": 100, "sizeleft": 50},
        ]
        first = MediaAttentionService._series_queue_evidence(1, records)
        second = MediaAttentionService._series_queue_evidence(1, list(reversed(records)))
        self.assertEqual(first, second)
        self.assertTrue(first["active"])
        failure = MediaAttentionService._series_queue_evidence(1, [records[0]])
        self.assertFalse(failure["completed"])
        self.assertEqual(MediaAttentionService._resolve_tv_stage({"id": 1}, SimpleNamespace(caught_up=False), failure)[0], PipelineStage.SONARR_SEARCHING)

    def test_duplicate_request_selection_prefers_newest_then_id(self):
        requests = [
            {"id": 2, "type": "tv", "status": 2, "createdAt": "2025-01-01T00:00:00Z", "media": {"tmdbId": 7}},
            {"id": 1, "type": "tv", "status": 2, "createdAt": "2026-01-01T00:00:00Z", "media": {"tmdbId": 7}},
            {"id": 5, "type": "tv", "status": 2, "createdAt": "invalid", "media": {"tmdbId": 8}},
            {"id": 6, "type": "tv", "status": 2, "media": {"tmdbId": 8}},
        ]
        selected = MediaAttentionService._deduplicate_tv_requests(requests)
        self.assertEqual([(item["media"]["tmdbId"], item["id"]) for item in selected], [(7, 1), (8, 6)])
