from pydantic import BaseModel


class MaturityCoverage(BaseModel):

    pct_with_steward: int
    pct_certified: int
    pct_with_active_contract: int
    pct_pii_with_documented_purpose: int


class MaturityAverageScores(BaseModel):

    governance_score: int
    privacy_score: int
    quality_score: int


class MaturityOverview(BaseModel):

    total_datasets: int
    # NOT_STARTED / AD_HOC / REACTIVE / MANAGED / TRUSTED
    level: str
    overall_score: int
    coverage: MaturityCoverage
    average_scores: MaturityAverageScores
    recommended_next_steps: list[str]
