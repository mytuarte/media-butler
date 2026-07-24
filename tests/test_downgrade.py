import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from models.media_analysis import MovieAnalysis, SeriesAnalysis
from services.command_service import CommandService
from services.downgrade_service import DowngradeService
from views.downgrade_view import DowngradeConfirmationView, DowngradeView


def release(size, resolution="1080p", languages=None, title="Film.1080p.WEB-DL", **extra):
    return {"size": size, "resolution": resolution, "languages": languages or ["English"], "releaseTitle": title, **extra}


class DowngradeServiceTests(unittest.TestCase):
    def media(self, media_type="movie"):
        return SimpleNamespace(id=7, title="Film", media_type=media_type)

    def test_movie_filters_and_ranks_largest_first_with_top_five(self):
        releases = [release(n) for n in (10, 80, 60, 50, 40, 30, 20)] + [release(15, "720p"), release(15, languages=["French"]), release(100)]
        service = DowngradeService(Mock(manual_search=Mock(return_value=releases)), Mock())
        candidates = service.candidates(self.media(), MovieAnalysis("movie", "Film", 2020, 100, 1))
        self.assertEqual([item.size_bytes for item in candidates], [80, 60, 50, 40, 30])
        self.assertEqual(candidates[0].savings_percent, 20)

    def test_movie_requires_1080p_english_known_smaller_and_usable(self):
        releases = [release(20, "720p"), release(20, languages=["French"]), release(20, title="Film.CAM"), release(20, rejections=["not approved"]), {"resolution":"1080p", "languages":["English"]}, release(100)]
        candidates = DowngradeService(Mock(manual_search=Mock(return_value=releases)), Mock()).candidates(self.media(), MovieAnalysis("movie", "Film", 2020, 100, 1))
        self.assertEqual(candidates, [])

    def test_tv_allows_720p(self):
        sonarr = Mock(manual_search=Mock(return_value=[release(20, "720p")]))
        candidates = DowngradeService(Mock(), sonarr).candidates(self.media("series"), SeriesAnalysis("series", "Film", 2020, 100, 1))
        self.assertEqual(len(candidates), 1)

    def test_manual_search_is_read_only(self):
        radarr, sonarr = Mock(), Mock()
        radarr.manual_search.return_value = []
        DowngradeService(radarr, sonarr).candidates(self.media(), MovieAnalysis("movie", "Film", 2020, 100, 1))
        self.assertEqual([call for call in radarr.mock_calls if any(word in call[0].lower() for word in ("post", "put", "delete"))], [])


class DowngradeUiTests(unittest.IsolatedAsyncioTestCase):
    def test_command_registered(self):
        self.assertIn("downgrade", CommandService().commands)

    def test_candidate_view_and_confirmation_screen(self):
        candidate = DowngradeService._normalize(release(40), "Film", 100, 1080)
        embed = DowngradeView.build("Film", 100, "Remux-2160p", [candidate])
        self.assertEqual(embed.title, "♻ Replacement Candidates")
        confirmation = DowngradeView.confirmation_embed("Film", 100, "Remux-2160p", candidate)
        self.assertEqual(confirmation.title, "Replace Film?")

    async def test_confirm_performs_no_write_action(self):
        candidate = DowngradeService._normalize(release(40), "Film", 100, 1080)
        parent = DowngradeView("Film", 100, "Remux", [candidate], 1)
        view = DowngradeConfirmationView(parent, candidate)
        response = Mock(); response.send_message = AsyncMock()
        interaction = SimpleNamespace(user=SimpleNamespace(id=1), response=response)
        await view.confirm(interaction)
        response.send_message.assert_called_once_with("Download workflow not implemented yet.", ephemeral=True)
