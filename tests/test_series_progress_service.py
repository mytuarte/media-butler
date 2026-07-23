from datetime import datetime, timezone
import unittest

from services.series_progress_service import SeriesProgressService


class FakeSonarr:
    def __init__(self, episodes):
        self.episodes = episodes
        self.refreshes = []

    def get_episodes(self, series_id, refresh=False):
        self.refreshes.append(refresh)
        return self.episodes


class SeriesProgressServiceTests(unittest.TestCase):
    def test_only_released_normal_episodes_count_and_fresh_read_is_used(self):
        sonarr = FakeSonarr([
            {"seasonNumber": 0, "episodeNumber": 1, "airDateUtc": "2020-01-01T00:00:00Z", "hasFile": False},
            {"seasonNumber": 1, "episodeNumber": 1, "airDateUtc": "2020-01-01T00:00:00Z", "hasFile": True},
            {"seasonNumber": 1, "episodeNumber": 2, "airDateUtc": "2030-01-01T00:00:00Z", "hasFile": False},
            {"seasonNumber": 1, "episodeNumber": 3, "hasFile": False},
            {"seasonNumber": 1, "episodeNumber": 4, "airDateUtc": "2020-01-02T00:00:00Z", "hasFile": False},
        ])
        progress = SeriesProgressService(sonarr).evaluate(42, datetime(2025, 1, 1, tzinfo=timezone.utc))
        self.assertEqual(progress.released_episode_keys, ("S01E01", "S01E04"))
        self.assertEqual(progress.arr_imported_episode_keys, ("S01E01",))
        self.assertEqual(progress.missing_episode_keys, ("S01E04",))
        self.assertFalse(progress.caught_up)
        self.assertEqual(sonarr.refreshes, [True])

    def test_caught_up_requires_at_least_one_released_episode(self):
        now = datetime(2025, 1, 1, tzinfo=timezone.utc)
        self.assertFalse(SeriesProgressService(FakeSonarr([])).evaluate(1, now).caught_up)
        self.assertTrue(SeriesProgressService(FakeSonarr([
            {"seasonNumber": 1, "episodeNumber": 1, "airDate": "2020-01-01", "hasFile": True}
        ])).evaluate(1, now).caught_up)
