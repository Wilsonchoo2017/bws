"""Recommendation generation for Bricklink items.

Combines demand and availability analysis to generate investment recommendations.
"""

from datetime import UTC, datetime

from bws.types.models import (
    Action,
    AnalysisScore,
    ProductRecommendation,
    Urgency,
)


# Use UTC constant to ensure import is retained
_UTC = UTC


def _determine_action(overall_score: int, confidence: float) -> Action:
    """Determine investment action based on score and confidence."""
    # Require higher scores when confidence is low
    confidence_adjusted = overall_score * confidence

    if confidence_adjusted >= 75:
        return Action.STRONG_BUY
    if confidence_adjusted >= 55:
        return Action.BUY
    if confidence_adjusted >= 35:
        return Action.HOLD
    return Action.SKIP


def _determine_urgency(
    demand_score: AnalysisScore | None,
    availability_score: AnalysisScore | None,
) -> Urgency:
    """Determine urgency based on availability and demand trends."""
    if not availability_score:
        return Urgency.NO_RUSH

    avail_value = availability_score.value

    # Boost urgency if demand is also high
    demand_boost = 0
    if demand_score and demand_score.value >= 70:
        demand_boost = 10

    adjusted_value = avail_value + demand_boost

    # High availability score means scarce = urgent
    if adjusted_value >= 80:
        return Urgency.URGENT
    if adjusted_value >= 65:
        return Urgency.MODERATE
    if adjusted_value >= 45:
        return Urgency.LOW
    return Urgency.NO_RUSH


def _identify_risks(
    demand_score: AnalysisScore | None,
    availability_score: AnalysisScore | None,
    overall_confidence: float,
) -> tuple[str, ...]:
    """Identify investment risks."""
    risks = []

    if overall_confidence < 0.5:
        risks.append("Limited data - analysis may be unreliable")

    if demand_score:
        if demand_score.value < 40:
            risks.append("Low demand may limit resale potential")
        if demand_score.confidence < 0.5:
            risks.append("Demand data is sparse")
        if "decline" in demand_score.reasoning.lower():
            risks.append("Declining demand trend detected")

    if availability_score:
        if availability_score.value < 30:
            risks.append("High availability may suppress price growth")
        if "widely available" in availability_score.reasoning.lower():
            risks.append("Item is still widely available at retail")

    if not risks:
        risks.append("No significant risks identified")

    return tuple(risks)


def _identify_opportunities(
    demand_score: AnalysisScore | None,
    availability_score: AnalysisScore | None,
) -> tuple[str, ...]:
    """Identify investment opportunities."""
    opportunities = []

    if demand_score:
        if demand_score.value >= 70:
            opportunities.append("Strong demand supports price growth")
        if "upward trend" in demand_score.reasoning.lower():
            opportunities.append("Demand is trending upward")
        if demand_score.value >= 50 and "high transaction" in demand_score.reasoning.lower():
            opportunities.append("Active market with good liquidity")

    if availability_score:
        if availability_score.value >= 70:
            opportunities.append("Limited supply creates scarcity value")
        if "retired" in availability_score.reasoning.lower():
            opportunities.append("Retired status increases collectibility")
        if "appreciation" in availability_score.reasoning.lower():
            opportunities.append("Price appreciation trend detected")

    if not opportunities:
        opportunities.append("Standard investment profile")

    return tuple(opportunities)


def generate_recommendation(
    item_id: str,
    demand_score: AnalysisScore | None,
    availability_score: AnalysisScore | None,
) -> ProductRecommendation:
    """Generate an investment recommendation.

    Args:
        item_id: Bricklink item ID
        demand_score: Demand analysis score (optional)
        availability_score: Availability analysis score (optional)

    Returns:
        ProductRecommendation with action and supporting analysis
    """
    # Calculate overall score (weighted average of available scores)
    scores = []
    weights = []

    if demand_score:
        scores.append(demand_score.value)
        weights.append(0.5)

    if availability_score:
        scores.append(availability_score.value)
        weights.append(0.5)

    if not scores:
        # No analysis data available
        overall_value = 50
        overall_confidence = 0.0
        overall_reasoning = "Insufficient data for analysis"
    else:
        # Normalize weights
        total_weight = sum(weights)
        normalized_weights = [w / total_weight for w in weights]

        overall_value = int(sum(s * w for s, w in zip(scores, normalized_weights, strict=True)))

        # Combine confidences
        confidences = []
        if demand_score:
            confidences.append(demand_score.confidence)
        if availability_score:
            confidences.append(availability_score.confidence)
        overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        # Build reasoning
        reasons = []
        if demand_score:
            reasons.append(f"Demand: {demand_score.value}/100")
        if availability_score:
            reasons.append(f"Availability: {availability_score.value}/100")
        overall_reasoning = ". ".join(reasons)

    overall = AnalysisScore(
        value=overall_value,
        confidence=overall_confidence,
        reasoning=overall_reasoning,
    )

    action = _determine_action(overall_value, overall_confidence)
    urgency = _determine_urgency(demand_score, availability_score)
    risks = _identify_risks(demand_score, availability_score, overall_confidence)
    opportunities = _identify_opportunities(demand_score, availability_score)

    return ProductRecommendation(
        item_id=item_id,
        overall=overall,
        action=action,
        urgency=urgency,
        risks=risks,
        opportunities=opportunities,
        demand_score=demand_score,
        availability_score=availability_score,
        analyzed_at=datetime.now(tz=_UTC),
    )
