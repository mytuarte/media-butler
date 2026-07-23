import unittest
from unittest.mock import Mock, patch

from services.sonarr_service import SonarrService
from config import Config


class SonarrQueueTests(unittest.TestCase):
    def response(self, payload):
        response = Mock()
        response.json.return_value = payload
        return response

    @patch("services.sonarr_service.requests.get")
    def test_one_page_uses_expected_request(self, get):
        get.return_value = self.response({"totalRecords": 2, "records": [{"id": 1}, {"id": 2}]})
        self.assertEqual(SonarrService().get_queue(), [{"id": 1}, {"id": 2}])
        get.return_value.raise_for_status.assert_called_once()
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"], {"page": 1, "pageSize": 1000, "includeEpisode": "true", "includeSeries": "true"})
        self.assertEqual(get.call_args.kwargs["timeout"], 10)
        self.assertEqual(get.call_args.kwargs["headers"], {"X-Api-Key": Config.SONARR_API_KEY})
        self.assertEqual(get.call_args.args[0], f"{Config.SONARR_URL}/api/v3/queue")

    @patch("services.sonarr_service.requests.get")
    def test_pages_list_empty_and_malformed_responses(self, get):
        get.side_effect = [self.response({"totalRecords": 3, "records": [{"id": 1}]}), self.response({"totalRecords": 3, "records": [{"id": 2}]}), self.response({"totalRecords": 3, "records": [{"id": 3}]})]
        self.assertEqual([item["id"] for item in SonarrService().get_queue()], [1, 2, 3])
        self.assertEqual([call.kwargs["params"]["page"] for call in get.call_args_list], [1, 2, 3])
        get.reset_mock(); get.side_effect = None; get.return_value = self.response([])
        self.assertEqual(SonarrService().get_queue(), [])
        for payload in (None, {}, {"totalRecords": "2", "records": []}, {"totalRecords": -1, "records": []}):
            get.reset_mock(); get.return_value = self.response(payload)
            with self.assertRaises(ValueError): SonarrService().get_queue()

    @patch("services.sonarr_service.requests.get")
    def test_incomplete_and_repeated_pages_raise(self, get):
        get.side_effect = [self.response({"totalRecords": 3, "records": [{"id": 1}]}), self.response({"totalRecords": 3, "records": []})]
        with self.assertRaisesRegex(ValueError, "ended before"): SonarrService().get_queue()
        get.side_effect = [self.response({"totalRecords": 3, "records": [{"id": 1}]}), self.response({"totalRecords": 3, "records": [{"id": 1}]})]
        with self.assertRaisesRegex(ValueError, "repeated"): SonarrService().get_queue()
