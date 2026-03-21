from typing import List
from common.schemas import SectorMetrics, RiskScore, RiskLevel


class SectorRiskScorer:
    """
    Calculates risk scores for financial sectors based on fundamental metrics.
    Deterministic implementation strictly following project rules.
    """

    def __init__(self):
        # Weights for risk factors (must sum to 1.0)
        self.weights = {
            "volatility": 0.4,
            "beta": 0.3,
            "debt_to_equity": 0.2,
            "pe_ratio": 0.1,
        }

        # Benchmarks for normalization (simplified for this task)
        self.benchmarks = {
            "volatility": 0.2,  # 20% annualized volatility is standard
            "beta": 1.0,  # Market beta is 1.0
            "debt_to_equity": 1.5,  # Debt/Equity ratio of 1.5 is standard
            "pe_ratio": 20.0,  # PE ratio of 20 is standard
        }

    def calculate_risk(self, metrics: List[SectorMetrics]) -> List[RiskScore]:
        """
        Computes normalized risk scores (0-100) for a list of sectors.
        """
        results = []
        for metric in metrics:
            # 1. Normalize metrics against benchmarks
            # Higher volatility = higher risk
            norm_volatility = metric.volatility / self.benchmarks["volatility"]

            # Higher beta = higher risk
            norm_beta = metric.beta / self.benchmarks["beta"]

            # Higher debt/equity = higher risk
            norm_debt = metric.debt_to_equity / self.benchmarks["debt_to_equity"]

            # Higher PE = higher valuation risk (simplified assumption)
            norm_pe = metric.pe_ratio / self.benchmarks["pe_ratio"]

            # 2. Calculate raw weighted score
            raw_score = (
                (norm_volatility * self.weights["volatility"])
                + (norm_beta * self.weights["beta"])
                + (norm_debt * self.weights["debt_to_equity"])
                + (norm_pe * self.weights["pe_ratio"])
            )

            # 3. Scale to 0-100 range
            # Assume raw_score of 1.0 is average risk (50/100)
            scaled_score = min(max(raw_score * 50, 0), 100)

            # 4. Determine risk level
            risk_level = self._determine_risk_level(scaled_score)

            # 5. Identify contributing factors
            factors = []
            if norm_volatility > 1.2:
                factors.append("High Volatility")
            if norm_beta > 1.2:
                factors.append("High Market Sensitivity")
            if norm_debt > 1.2:
                factors.append("High Leverage")
            if norm_pe > 1.2:
                factors.append("High Valuation")

            results.append(
                RiskScore(
                    sector_name=metric.sector_name,
                    risk_score=round(scaled_score, 2),
                    risk_level=risk_level,
                    contributing_factors=factors,
                )
            )

        return results

    def _determine_risk_level(self, score: float) -> RiskLevel:
        if score < 30:
            return RiskLevel.LOW
        elif score < 60:
            return RiskLevel.MEDIUM
        elif score < 80:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL
