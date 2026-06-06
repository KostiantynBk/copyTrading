import unittest

from copytrade_monitor.ai_analyzer import _infer_explicit_trade_signal


class InferExplicitTradeSignalTests(unittest.TestCase):
    def test_detects_company_name_buy_without_ticker(self) -> None:
        signal = _infer_explicit_trade_signal(
            "Bought some Microsoft because it turned into a Micro Cap\n\nI'll hold for 2-3 years"
        )

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertTrue(signal.is_trade_signal)
        self.assertEqual(signal.action, "buy")
        self.assertEqual(signal.company_name, "Microsoft")
        self.assertIsNone(signal.ticker)
        self.assertEqual(signal.asset_type, "equity")

    def test_detects_multi_word_company_name(self) -> None:
        signal = _infer_explicit_trade_signal("Started a position in Bank of America for the long term")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.company_name, "Bank of America")
        self.assertEqual(signal.action, "buy")

    def test_ignores_trade_language_without_asset_reference(self) -> None:
        signal = _infer_explicit_trade_signal("Bought some more because the chart looks better now")

        self.assertIsNone(signal)

    def test_detects_back_in_company_signal(self) -> None:
        signal = _infer_explicit_trade_signal("Back in Microsoft for 2-3 years")

        self.assertIsNotNone(signal)
        assert signal is not None
        self.assertEqual(signal.action, "buy")
        self.assertEqual(signal.company_name, "Microsoft")


if __name__ == "__main__":
    unittest.main()
