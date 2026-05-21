"""
Pydantic schemas for structured grading output.

These models are used with LangChain's `with_structured_output()` method
to get typed, validated responses directly from the LLM - no parsing needed.
"""

from pydantic import BaseModel, Field
from typing import List


class CriterionScore(BaseModel):
    """Score for a single rubric criterion."""
    criterion_name: str = Field(description="Name of the grading criterion")
    score: int = Field(ge=0, description="Points awarded for this criterion")
    max_points: int = Field(ge=0, description="Maximum possible points")
    performance_level: str = Field(description="Performance level: Outstanding/Excellent/Good/Fair/Poor")
    reasoning: str = Field(description="Brief explanation for this score")


class SceneGradingResult(BaseModel):
    """Structured output for scene grading."""
    overall_score: int = Field(ge=0, le=100, description="Overall scene score from 0-100")
    criteria_breakdown: List[CriterionScore] = Field(default_factory=list)

    # Self-audit fields — force chain-of-thought before committing to a score
    score_rationale: str = Field(
        description=(
            "One sentence per rubric criterion citing specific phrases from the student's "
            "conversation that justify the awarded score. Must quote the student directly. "
            "If no rubric criteria exist, cite specific evidence from the conversation."
        )
    )
    inflation_check_passed: bool = Field(
        description=(
            "True only if: (1) the overall_score is consistent with the criteria breakdown "
            "averages, and (2) no criterion was awarded an Outstanding score without a direct "
            "quote from the student's response as evidence in the reasoning field."
        )
    )

    # Qualitative assessment
    business_thinking_quality: str = Field(description="Assessment of business thinking demonstrated")
    key_strengths: str = Field(description="Key strengths demonstrated, or 'None identified'")
    areas_for_improvement: str = Field(description="Main areas needing improvement")

    # Feedback
    actionable_recommendations: str = Field(description="Specific recommendations for improvement")


class OverallGradingResult(BaseModel):
    """Structured output for overall simulation grading."""
    overall_score: int = Field(ge=0, le=100, description="Overall simulation score from 0-100")

    # Summary
    performance_summary: str = Field(description="Summary of performance across the simulation")
    key_strengths: str = Field(description="Key strengths demonstrated")
    areas_for_improvement: str = Field(description="Main areas for improvement")

    # Feedback
    actionable_recommendations: str = Field(description="Specific recommendations")
    business_acumen_insights: str = Field(description="Insights on business acumen development")
