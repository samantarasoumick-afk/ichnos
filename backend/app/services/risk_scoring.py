"""
Pure risk-scoring math - no DB access, so it's trivial to unit test
and impossible for a stored score to drift out of sync with its
inputs, since nothing here is ever persisted.

Likelihood and impact are each LOW/MEDIUM/HIGH (1/2/3). The inherent
score is their product (range 1-9, only {1,2,3,4,6,9} are reachable),
bucketed into a level. The residual score/level accounts for linked
Controls that are actually marked EFFECTIVE - an uncontrolled risk's
residual equals its inherent value; each effective control halves the
residual score (floor), which is a deliberately simple model (real GRC
tooling often uses much more elaborate control-weighting) chosen so
the effect of adding a working control is immediately visible without
requiring a probability model nobody will actually maintain.
"""

LEVEL_VALUES = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


def _level_value(level: str) -> int:
    return LEVEL_VALUES.get((level or "").upper(), 2)


def score_to_level(score: int) -> str:
    if score <= 2:
        return "LOW"
    if score <= 4:
        return "MEDIUM"
    return "HIGH"


def inherent_score(likelihood: str, impact: str) -> int:
    return _level_value(likelihood) * _level_value(impact)


def residual_score(likelihood: str, impact: str, effective_control_count: int) -> int:
    score = inherent_score(likelihood, impact)

    for _ in range(max(0, effective_control_count)):
        score = max(1, score // 2)

    return score


def compute_risk_scores(likelihood: str, impact: str, effective_control_count: int) -> dict:

    inherent = inherent_score(likelihood, impact)
    residual = residual_score(likelihood, impact, effective_control_count)

    return {
        "inherent_score": inherent,
        "inherent_level": score_to_level(inherent),
        "residual_score": residual,
        "residual_level": score_to_level(residual),
    }
