"""Analysis services for investment recommendations."""

from bws.services.analysis.availability import analyze_availability
from bws.services.analysis.demand import analyze_demand
from bws.services.analysis.quality import analyze_quality
from bws.services.analysis.recommendation import generate_recommendation


__all__ = [
    "analyze_availability",
    "analyze_demand",
    "analyze_quality",
    "generate_recommendation",
]
