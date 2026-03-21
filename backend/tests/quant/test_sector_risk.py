import unittest
from common.schemas import SectorMetrics, RiskLevel
from quant.sector_risk import SectorRiskScorer


class TestSectorRiskScorer(unittest.TestCase):
    def setUp(self):
        self.scorer = SectorRiskScorer()

    def test_low_risk(self):
        metrics = SectorMetrics(
            sector_name="Utilities",
            volatility=0.1,  # half benchmark
            beta=0.5,  # half benchmark
            pe_ratio=10.0,  # half benchmark
            debt_to_equity=0.75,  # half benchmark
        )
        score = self.scorer.calculate_risk([metrics])[0]
        self.assertLess(score.risk_score, 30)
        self.assertEqual(score.risk_level, RiskLevel.LOW)
        self.assertEqual(len(score.contributing_factors), 0)

    def test_high_risk(self):
        metrics = SectorMetrics(
            sector_name="Tech",
            volatility=0.4,  # double benchmark
            beta=2.0,  # double benchmark
            pe_ratio=40.0,  # double benchmark
            debt_to_equity=3.0,  # double benchmark
        )
        score = self.scorer.calculate_risk([metrics])[0]
        self.assertGreater(score.risk_score, 80)
        self.assertEqual(score.risk_level, RiskLevel.CRITICAL)
        self.assertTrue("High Volatility" in score.contributing_factors)
        self.assertTrue("High Market Sensitivity" in score.contributing_factors)
        self.assertTrue("High Leverage" in score.contributing_factors)
        self.assertTrue("High Valuation" in score.contributing_factors)

    def test_average_risk(self):
        metrics = SectorMetrics(
            sector_name="Market",
            volatility=0.2,
            beta=1.0,
            pe_ratio=20.0,
            debt_to_equity=1.5,
        )
        score = self.scorer.calculate_risk([metrics])[0]
        # Should be around 50
        self.assertAlmostEqual(score.risk_score, 50.0, delta=5.0)
        self.assertEqual(score.risk_level, RiskLevel.MEDIUM)

    def test_zero_values(self):
        metrics = SectorMetrics(
            sector_name="ZeroRisk",
            volatility=0.0,
            beta=0.0,
            pe_ratio=0.0,
            debt_to_equity=0.0,
        )
        score = self.scorer.calculate_risk([metrics])[0]
        self.assertEqual(score.risk_score, 0.0)
        self.assertEqual(score.risk_level, RiskLevel.LOW)

    def test_batch_processing(self):
        metrics1 = SectorMetrics(
            sector_name="Safe",
            volatility=0.1,
            beta=0.5,
            pe_ratio=10.0,
            debt_to_equity=0.75,
        )
        metrics2 = SectorMetrics(
            sector_name="Risky",
            volatility=0.4,
            beta=2.0,
            pe_ratio=40.0,
            debt_to_equity=3.0,
        )
        scores = self.scorer.calculate_risk([metrics1, metrics2])
        self.assertEqual(len(scores), 2)
        self.assertEqual(scores[0].sector_name, "Safe")
        self.assertEqual(scores[1].sector_name, "Risky")
        self.assertEqual(scores[0].risk_level, RiskLevel.LOW)
        self.assertEqual(scores[1].risk_level, RiskLevel.CRITICAL)


if __name__ == "__main__":
    unittest.main()
