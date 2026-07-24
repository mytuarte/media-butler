import unittest
from models.media_analysis import MovieAnalysis, SeasonAnalysis, SeriesAnalysis
from views.analyze_view import AnalyzeView, format_bytes

class AnalyzeViewTests(unittest.TestCase):
    def test_limits_are_hard_for_arbitrarily_long_movie_metadata(self):
        long = "x" * 10000
        analysis = MovieAnalysis("movie", long, 2020, 1, 1, file_relative_path=long, original_release_name=long, warnings=[long] * 10)
        embed = AnalyzeView.build(analysis)
        total = len(embed.title) + len(embed.description or "")
        for field in embed.fields:
            self.assertLessEqual(len(field.name), 256)
            self.assertLessEqual(len(field.value), 1024)
            total += len(field.name) + len(field.value)
        self.assertLessEqual(len(embed.fields), 25)
        self.assertLessEqual(total, 6000)
    def test_unavailable_seasons_sort_after_known_including_zero(self):
        seasons = [SeasonAnalysis(2, 1, None, None), SeasonAnalysis(3, 1, 0, 0), SeasonAnalysis(1, 1, 10, 10)]
        analysis = SeriesAnalysis("series", "Series", 2020, 10, 3, seasons=seasons)
        embed = AnalyzeView.build(analysis)
        value = next(f.value for f in embed.fields if f.name == "Largest Seasons")
        self.assertLess(value.index("S01"), value.index("S03"))
        self.assertLess(value.index("S03"), value.index("S02"))
        self.assertIn("Total Size: Unavailable", value)
    def test_bytes_none_and_zero_are_distinct(self):
        self.assertEqual(format_bytes(None), "Unavailable")
        self.assertEqual(format_bytes(0), "0 B")
