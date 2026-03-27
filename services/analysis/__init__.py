"""Analysis services for investment recommendations."""

from services.analysis.availability import analyze_availability
from services.analysis.demand import analyze_demand
from services.analysis.quality import analyze_quality
from services.analysis.recommendation import generate_recommendation


__all__ = [
    "analyze_availability",
    "analyze_demand",
    "analyze_quality",
    "generate_recommendation",
]
