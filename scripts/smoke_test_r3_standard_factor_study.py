"""R3 独立研究计算的合成数据验证；不接触正式行情。"""
import unittest

from run_r3_standard_factor_study import (
    block_test, outcome, performance, portfolio, rank_ic, scores,
)


class R3Tests(unittest.TestCase):
    def test_standard_windows(self):
        closes = [100 * 1.001**i for i in range(253)]
        reversal, momentum, low_vol = scores(closes)
        self.assertAlmostEqual(reversal, -(1.001**20-1))
        self.assertAlmostEqual(momentum, 1.001**231-1)
        self.assertAlmostEqual(low_vol, 0)
        closes[-1] *= 1.1
        self.assertAlmostEqual(scores(closes)[1], momentum)
        self.assertLess(scores(closes)[2], low_vol)

    def test_missing_history_rejected(self):
        self.assertIsNone(scores([1]*252))
        self.assertIsNone(scores([1]*252+[float("nan")]))

    def test_future_missing_does_not_reassign_group(self):
        rows = [{"symbol": str(i), "score": i, "gross": .01*i,
                 "net": .01*i-.002, "stress": .01*i-.004, "state": "filled"} for i in range(10)]
        rows[-1].update(gross=None, net=None, stress=None, state="unknown_exit")
        result = portfolio(rows)
        self.assertIsNone(result["top_net"])
        self.assertIsNone(result["groups_gross"][-1])
        self.assertEqual(result["unknown_exits"], 1)
        self.assertAlmostEqual(result["groups_gross"][0], .005)

    def test_execution_and_two_sided_cost(self):
        a = ["date", 10, 11, 9, 10, 100, 1]
        b = ["date", 11, 12, 10, 11, 100, 1]
        self.assertAlmostEqual(outcome(a, b)["net"], .098)
        self.assertEqual(outcome(None, b)["state"], "cash_entry_unavailable")
        self.assertIsNone(outcome(a, None)["net"])
        self.assertEqual(outcome(["date", 10, 10, 10, 10, 100, 1], b)["gross"], 0)

    def test_nonoverlap_nav_and_unknown(self):
        self.assertAlmostEqual(performance([.1, -.1])["cumulative"], -.01)
        self.assertIsNone(performance([.1, None]))
        self.assertAlmostEqual(performance([.1, -.1])["period_end_max_drawdown"], -.1)

    def test_tied_ranks_and_bootstrap_repeatable(self):
        self.assertAlmostEqual(rank_ic([1, 1, 3, 4], [2, 2, 6, 8]), 1)
        values = [.01, -.02, .03]*16
        self.assertEqual(block_test(values), block_test(values))
        self.assertIsNone(block_test([.1]*10)["p_one_sided"])


if __name__ == "__main__":
    unittest.main()
