import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from ats import auction_cache
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher


class AuctionCacheTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"auction.sqlite3"
        self.patcher=patch.object(auction_cache,"_path",return_value=self.path)
        self.patcher.start();self.addCleanup(self.patcher.stop)

    def sample(self, price=10, observed="09:20:10"):
        return dict(date="2026-10-20",time_only="09:20",price=price,kind="auction_indicative",observed_at=observed)

    def fetcher(self):
        obj=TDXRealtimeFetcher.__new__(TDXRealtimeFetcher)
        obj._conn_lock=threading.RLock();obj.cache_pool=SimpleNamespace(is_trading_day=lambda day:True)
        return obj

    def test_cache_isolated_by_date_code_and_older_writer_cannot_replace_newer(self):
        auction_cache.save_samples("600001","2026-10-20",[self.sample()])
        auction_cache.save_samples("600001","2026-10-20",[self.sample(9,"09:20:00")])
        self.assertEqual(auction_cache.load_samples("600001","2026-10-20")[0]["price"],10)
        self.assertEqual(auction_cache.load_samples("600002","2026-10-20"),[])
        self.assertEqual(auction_cache.load_samples("600001","2026-10-21"),[])

    def test_reopen_after_0930_restores_today_without_modifying_trade_price(self):
        auction_cache.save_samples("600001","2026-10-20",[self.sample()])
        with patch("ats.tdx_realtime_fetcher.datetime") as clock:
            clock.now.return_value=datetime(2026,10,20,10,0)
            result=self.fetcher()._record_auction_snapshot(dict(code="600001",price=12,open_price=11))
        self.assertEqual(result["price"],12)
        self.assertEqual(result["open_price"],11)
        self.assertNotIn("market_phase",result)
        self.assertEqual(len(result["auction_samples"]),1)

    def test_indicative_kept_out_of_trade_and_final_open_saved_immediately(self):
        obj=self.fetcher()
        with patch("ats.tdx_realtime_fetcher.datetime") as clock:
            clock.now.return_value=datetime(2026,10,20,9,20)
            result=obj._record_auction_snapshot(dict(code="600001",price=9,open_price=0,bid1=10,ask1=10,volume=0))
            self.assertEqual(result["price"],9)
            self.assertEqual(result["auction_price"],10)
            clock.now.return_value=datetime(2026,10,20,9,25)
            obj._record_auction_snapshot(dict(code="600001",price=11,open_price=11,volume=100))
        rows=auction_cache.load_samples("600001","2026-10-20")
        self.assertEqual(rows[-1]["kind"],"auction_open")
        self.assertEqual(rows[-1]["price"],11)

    def test_ramdisk_unavailable_preserves_memory_without_creating_ssd_cache(self):
        with patch.object(auction_cache,"_path",side_effect=RuntimeError("unavailable")), patch("ats.tdx_realtime_fetcher.datetime") as clock:
            clock.now.return_value=datetime(2026,10,20,9,20)
            result=self.fetcher()._record_auction_snapshot(dict(code="600001",price=9,bid1=10,ask1=10))
        self.assertEqual(len(result["auction_samples"]),1)
        self.assertFalse(self.path.exists())

    def test_c_toggles_memory_only_and_does_not_interfere_with_text_editing(self):
        from ats.ui.intraday_strategy_dialog import SBCIntradayChartDialog
        canvas=SimpleNamespace(show_auction_chart=True,auction_samples=[self.sample()],update=Mock())
        dialog=SimpleNamespace(canvas=canvas,lbl_info=Mock())
        with patch("ats.ui.styles.is_editing_text",return_value=False):
            SBCIntradayChartDialog._on_shortcut_c_activated(dialog)
            self.assertFalse(canvas.show_auction_chart)
            SBCIntradayChartDialog._on_shortcut_c_activated(dialog)
            self.assertTrue(canvas.show_auction_chart)
        with patch("ats.ui.styles.is_editing_text",return_value=True):
            SBCIntradayChartDialog._on_shortcut_c_activated(dialog)
        self.assertTrue(canvas.show_auction_chart)
        self.assertEqual(canvas.update.call_count,2)
