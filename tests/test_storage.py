import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from copytrade_monitor.models import AnalysisRecord, ObservedPost, TradeSignal
from copytrade_monitor.storage import append_analysis_record, ensure_directories


class StorageTests(unittest.TestCase):
    def test_ensure_directories_creates_analysis_parent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cache_path = base / "data" / "cache.json"
            reports_dir = base / "data" / "reports"
            analyses_path = base / "data" / "analyses.jsonl"

            ensure_directories(cache_path, reports_dir, analyses_path)

            self.assertTrue(cache_path.parent.exists())
            self.assertTrue(reports_dir.exists())
            self.assertTrue(analyses_path.parent.exists())

    def test_append_analysis_record_writes_jsonl_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            analyses_path = Path(tmp) / "data" / "analyses.jsonl"
            analyses_path.parent.mkdir(parents=True, exist_ok=True)
            record = AnalysisRecord(
                post=ObservedPost(
                    post_id="123",
                    handle="NoLimitGains",
                    text="Bought some Microsoft because it turned into a Micro Cap",
                    url="https://x.com/test/status/123",
                    captured_at=datetime.now(UTC),
                ),
                signal=TradeSignal(
                    is_trade_signal=True,
                    action="buy",
                    sentiment="bullish",
                    company_name="Microsoft",
                    asset_type="equity",
                    confidence=0.88,
                    rationale="Detected an explicit position-management update in the post text mentioning Microsoft.",
                    evidence_text="Bought some Microsoft because it turned into a Micro Cap",
                    detection_method="heuristic",
                ),
                analyzed_at=datetime.now(UTC),
            )

            append_analysis_record(analyses_path, record)

            lines = analyses_path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["post"]["handle"], "NoLimitGains")
            self.assertTrue(payload["signal"]["is_trade_signal"])
            self.assertEqual(payload["signal"]["company_name"], "Microsoft")


if __name__ == "__main__":
    unittest.main()
