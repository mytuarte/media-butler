import unittest
from models.media_result import MediaResult
from services.analyze_service import AnalyzeService
from services.analyze_service import languages, resolution
class R:
 def __init__(self,p):self.p=p
 def get_movie_by_id(self,_):return self.p
class S:
 def __init__(self,files,eps):self.files=files;self.eps=eps
 def get_series_by_id(self,_):return {}
 def get_episodes(self,_,refresh=False):assert refresh;return self.eps
 def get_episode_files(self,_):return self.files
class P:
 def evaluate(self,_): return type("Progress", (), {"released_count": 2, "imported_released_count": 1})()
class AnalyzeServiceTests(unittest.TestCase):
 def media(self,t='movie'):return MediaResult(1,t,'Title',2020,True,True,'','','')
 def test_movie_size_forms_and_metadata(self):
  payload={'runtime':60,'movieFile':{'size':'1024.9','quality':{'quality':{'name':'Remux','resolution':2160}},'relativePath':'movie.mkv','mediaInfo':{'videoCodec':'x265','videoDynamicRangeType':'HDR10','audioChannels':6,'audioLanguages':[{'name':'French'},'English','French']}}}
  a=AnalyzeService(R(payload),S([],[]),P()).analyze_movie(self.media());self.assertEqual((a.size_bytes,a.resolution,a.video_codec,a.audio_channels,a.audio_languages),(1024,'2160p','HEVC','5.1',['English','French']))
  self.assertIsNotNone(a.estimated_total_bitrate_mbps)
 def test_missing_boolean_and_zero_sizes(self):
  for value,expected in ((None,None),(True,None),(-1,None),(0,0)):
   a=AnalyzeService(R({'movieFile':{'size':value}}),S([],[]),P()).analyze_movie(self.media());self.assertEqual(a.size_bytes,expected)
 def test_series_unknown_sizes_and_unmatched_not_special(self):
  files=[{'id':1,'size':100},{'id':2},{'id':3,'size':0}];eps=[{'id':11,'episodeFileId':1,'seasonNumber':1,'episodeNumber':1},{'id':13,'episodeFileId':3,'seasonNumber':0,'episodeNumber':1}]
  a=AnalyzeService(R({}),S(files,eps),P()).analyze_series(self.media('series'));self.assertEqual((a.total_size_bytes,a.known_size_file_count,a.unknown_size_file_count,a.specials_file_count),(100,2,1,1));self.assertTrue(any(x.season_number is None for x in a.largest_episode_files))
 def test_multi_episode_file_is_physical_once(self):
  a=AnalyzeService(R({}),S([{'id':1,'size':10}],[{'episodeFileId':1,'seasonNumber':1,'episodeNumber':1},{'episodeFileId':1,'seasonNumber':1,'episodeNumber':2}]),P()).analyze_series(self.media('series'));self.assertEqual((a.file_count,a.total_size_bytes),(1,10))

class AnalyzeNormalizationTests(unittest.TestCase):
    def media(self, media_type='movie'):
        return MediaResult(1, media_type, 'Title', 2020, True, True, '', '', '')

    def test_resolution_labels_cover_dimensions_numeric_and_unknown_values(self):
        cases = {
            '3840x2160': '2160p', '1920x1080': '1080p',
            '1914x1080': '1080p', '1912x1080': '1080p',
            '1280x720': '720p', '720': '720p', '1080': '1080p',
            '2160p': '2160p', '3840X2160': '2160p',
            '  3840 x 2160  ': '2160p', 'unknown': 'unknown',
            '3840-by-2160': '3840-by-2160', '3840xnope': '3840xnope',
            '1024x500': '1024x500',
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(resolution(value), expected)

    def test_languages_normalize_split_deduplicate_and_sort(self):
        cases = (
            ('ger/eng/eng', ['English', 'German']),
            ('ENG, eng, English', ['English']),
            (['ger', 'eng', 'spa'], ['English', 'German', 'Spanish']),
            ([{'name': 'ger'}, {'name': 'English'}, {'name': 'eng'}], ['English', 'German']),
            (['ger/eng', 'spa, fre'], ['English', 'French', 'German', 'Spanish']),
            ('rus, klingon, EN', ['English', 'klingon', 'Russian']),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(languages(value), expected)

    def test_movie_and_series_resolutions_are_normalized(self):
        movie = AnalyzeService(R({'movieFile': {'mediaInfo': {'resolution': '3840x2160'}}}), S([], []), P()).analyze_movie(self.media())
        series = AnalyzeService(R({}), S([{'id': 1, 'mediaInfo': {'resolution': '1912X1080'}}], [{'episodeFileId': 1, 'seasonNumber': 1, 'episodeNumber': 1}]), P()).analyze_series(self.media('series'))
        self.assertEqual(movie.resolution, '2160p')
        self.assertEqual(series.resolution_distribution, {'1080p': 1})

    def test_duplicate_release_is_omitted_and_paths_are_sanitized(self):
        payload = {'movieFile': {'relativePath': '/media/movies/Film.mkv', 'sceneName': r'C:\releases\Film'}}
        analysis = AnalyzeService(R(payload), S([], []), P()).analyze_movie(self.media())
        self.assertEqual(analysis.file_relative_path, 'Film.mkv')
        self.assertIsNone(analysis.original_release_name)

    def test_distinct_release_is_retained_and_sanitized(self):
        payload = {'movieFile': {'relativePath': 'Film.mkv', 'sceneName': '/releases/Film.2160p-GROUP'}}
        analysis = AnalyzeService(R(payload), S([], []), P()).analyze_movie(self.media())
        self.assertEqual(analysis.original_release_name, 'Film.2160p-GROUP')

    def test_safe_paths_cover_posix_and_windows(self):
        from services.analyze_service import safe_relative_path
        self.assertEqual(safe_relative_path('/media/movies/title/file.mkv'), 'file.mkv')
        self.assertEqual(safe_relative_path(r'C:\Media\Movies\Title\file.mkv'), 'file.mkv')
        self.assertEqual(safe_relative_path(r'\\NAS\Media\Title\file.mkv'), 'file.mkv')
        self.assertEqual(safe_relative_path('Folder/Subfolder/file.mkv'), 'Folder/Subfolder/file.mkv')
        self.assertEqual(safe_relative_path('file.mkv'), 'file.mkv')

    def test_string_file_identifier_matches_numeric_episode_identifier(self):
        service = AnalyzeService(
            R({}),
            S([{'id': '12', 'size': 1}], [{'id': 9, 'episodeFileId': 12, 'seasonNumber': 1, 'episodeNumber': 2}]),
            P(),
        )
        result = service.analyze_series(AnalyzeServiceTests().media('series'))
        self.assertEqual(result.largest_episode_files[0].episode_number, 2)
