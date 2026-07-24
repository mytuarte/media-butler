import asyncio
import tempfile
import time
import unittest
from pathlib import Path

from models.overseerr_request import OverseerrRequest
from models.series_completion_notification import SeriesCompletionNotification
from services.series_completion_notification_service import SeriesCompletionNotificationService
from services.series_completion_notification_state_store import SeriesCompletionNotificationStateStore
from services.discord_service import DiscordService
from views.series_completion_notification_view import SeriesCompletionNotificationView

class Over:
    def __init__(self, request=None): self.request=request; self.calls=[]
    def get_request(self, tmdb_id, refresh=False): self.calls.append((tmdb_id,refresh)); return self.request
class Sonarr:
    def __init__(self, episodes=None, slow=False): self.episodes=episodes or self.base(); self.slow=slow; self.calls=[]; self.series={"id":9,"tmdbId":12,"title":"Weekly","year":2025}
    @staticmethod
    def base(): return [{"seasonNumber":0,"episodeNumber":1,"airDate":"2020-01-01","hasFile":False},{"seasonNumber":1,"episodeNumber":1,"airDate":"2020-01-01","hasFile":True},{"seasonNumber":1,"episodeNumber":2,"airDate":"2020-01-02","hasFile":True},{"seasonNumber":1,"episodeNumber":3,"airDate":"2999-01-01","hasFile":False}]
    def get_series_by_id(self, ident):
        self.calls.append("series");
        if self.slow: time.sleep(.1)
        return self.series if ident == 9 else None
    def get_episodes(self, ident, refresh=False): self.calls.append(("episodes",refresh)); return self.episodes
class Notify:
    def __init__(self, fail=False): self.sent=[]; self.fail=fail
    async def send_series_completion_notification(self,n):
        if self.fail: raise RuntimeError("send failed")
        await asyncio.sleep(0); self.sent.append(n)
class FailingStore(SeriesCompletionNotificationStateStore):
    def save(self, value): raise OSError("disk full")

class Tests(unittest.TestCase):
    def payload(self, **kw):
        p={"eventType":"Download","series":{"id":9},"episodes":[{"id":1}]};p.update(kw);return p
    def service(self, sonarr=None, overseerr=None, notify=None, store=None):
        store=store or SeriesCompletionNotificationStateStore(Path(tempfile.mkdtemp())/"state.json")
        return SeriesCompletionNotificationService(sonarr or Sonarr(), overseerr or Over(), notify or Notify(), store)
    def test_all_ignored_events_do_no_work(self):
        cases=[{},self.payload(eventType="Test"),self.payload(eventType="Grab"),self.payload(eventType="Rename"),self.payload(eventType="Health"),self.payload(eventType="ApplicationUpdate"),self.payload(eventType="Other"),self.payload(episodes=[]),self.payload(isUpgrade=True),self.payload(episodeFile={"isUpgrade":True}),self.payload(series={}),self.payload(seriesId="9")]
        for payload in cases:
            s=self.service(); self.assertFalse(asyncio.run(s.process(payload)));self.assertEqual(s.sonarr.calls,[]);self.assertEqual(s.overseerr.calls,[]);self.assertEqual(s.notification_service.sent,[])
    def test_explicit_overseerr_and_ids(self):
        over=Over(OverseerrRequest(1,2,3,"Mike",42,None,{})); sonarr=Sonarr(); s=self.service(sonarr,over)
        self.assertTrue(asyncio.run(s.process(self.payload(seriesId=9))))
        self.assertEqual(over.calls,[(12,True)]); self.assertFalse(hasattr(sonarr,"overseerr")); n=s.notification_service.sent[0];self.assertEqual((n.requester_name,n.requester_discord_id),("Mike",42))
    def test_concurrent_and_weekly_signature(self):
        s=self.service()
        async def run():
            first = await asyncio.gather(s.process(self.payload()),s.process(self.payload()))
            s.sonarr.episodes.append({"seasonNumber":1,"episodeNumber":3,"airDate":"2020-01-03","hasFile":True})
            second = await asyncio.gather(s.process(self.payload()),s.process(self.payload()))
            return first, second
        first, second = asyncio.run(run())
        self.assertEqual(first,[True,False]);self.assertEqual(second,[True,False]);self.assertEqual(len(s.notification_service.sent),2);self.assertEqual(len(s.state),1)
    def test_slow_sync_work_does_not_block_loop(self):
        s=self.service(sonarr=Sonarr(slow=True)); ticks=[]
        async def run():
            task=asyncio.create_task(s.process(self.payload())); await asyncio.sleep(.02); ticks.append(True); await task
        asyncio.run(run());self.assertEqual(ticks,[True])
    def test_delivery_and_save_failures_leave_state_retryable(self):
        s=self.service(notify=Notify(True));
        with self.assertRaises(RuntimeError): asyncio.run(s.process(self.payload()))
        self.assertEqual(s.state,{})
        s=self.service(store=FailingStore(Path(tempfile.mkdtemp())/"x.json"));
        with self.assertRaises(OSError): asyncio.run(s.process(self.payload()))
        self.assertEqual(s.state,{})
    def test_view_and_discord_id_contract(self):
        for name, ident, content in [("Mike",42,"<@42>"),("Mike",None,None),(None,42,"<@42>"),(None,None,None),("Mike",0,None),("Mike",-1,None),("Mike",True,None),("Mike","42",None)]:
            n=SeriesCompletionNotification("Weekly",2025,name,ident,2,2); embed=SeriesCompletionNotificationView.build(n)
            self.assertNotIn("<@",embed.fields[1].value);self.assertIn("Weekly",embed.title)
            self.assertEqual(DiscordService._valid_discord_user_id(ident), content is not None)

class RestoredCompletionTests(Tests):
    def test_partial_zero_missing_series_and_tmdb_do_not_send(self):
        partial = Sonarr(); partial.episodes[2]["hasFile"] = False
        self.assertFalse(asyncio.run(self.service(sonarr=partial).process(self.payload())))
        zero = Sonarr(episodes=[{"seasonNumber": 1, "episodeNumber": 1, "airDate": "2999-01-01", "hasFile": True}])
        self.assertFalse(asyncio.run(self.service(sonarr=zero).process(self.payload())))
        missing = Sonarr(); missing.series = None
        self.assertFalse(asyncio.run(self.service(sonarr=missing).process(self.payload())))
        no_tmdb = Sonarr(); no_tmdb.series = {"id": 9, "title": "No TMDb"}
        self.assertFalse(asyncio.run(self.service(sonarr=no_tmdb).process(self.payload())))
    def test_refresh_restart_and_state_written(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SeriesCompletionNotificationStateStore(Path(directory) / "nested" / "state.json")
            first = self.service(store=store)
            self.assertTrue(asyncio.run(first.process(self.payload())))
            self.assertEqual(first.sonarr.calls[-1], ("episodes", True))
            self.assertTrue(store.state_file.exists()); self.assertTrue(first.state)
            restarted = self.service(store=store)
            self.assertFalse(asyncio.run(restarted.process(self.payload())))
            self.assertEqual(restarted.notification_service.sent, [])
    def test_duplicate_bypasses_failing_overseerr(self):
        over = Over(); service = self.service(overseerr=over)
        self.assertTrue(asyncio.run(service.process(self.payload())))
        calls = len(over.calls)
        def boom(*args, **kwargs): raise RuntimeError("Overseerr down")
        over.get_request = boom
        self.assertFalse(asyncio.run(service.process(self.payload())))
        self.assertEqual(calls, 1)
