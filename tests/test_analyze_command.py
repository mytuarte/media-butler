import asyncio
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from commands.analyze_command import AnalyzeCommand


class AnalyzeCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_search_does_not_block_event_loop(self):
        responsive = threading.Event()
        test_case = self

        class SlowMediaService:
            def search(self, query):
                time.sleep(0.05)
                test_case.assertTrue(responsive.is_set())
                return []

        message = SimpleNamespace(
            content="!analyze Example",
            author=SimpleNamespace(id=1),
            channel=SimpleNamespace(send=self._send),
        )
        with patch("commands.analyze_command.MediaService", SlowMediaService):
            command = AnalyzeCommand()
            await asyncio.gather(command.execute(message), self._set_event(responsive))

    async def _send(self, *args, **kwargs):
        return None

    @staticmethod
    async def _set_event(event):
        await asyncio.sleep(0.01)
        event.set()
