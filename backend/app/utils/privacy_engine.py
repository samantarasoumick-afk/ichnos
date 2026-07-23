"""
Column-level sensitive-data classification.

Combines two signals:
  1. Name heuristics - fast, no data access required, catches the
     common case (a column literally called "email").
  2. Value sampling - checks a handful of actual sampled values
     against known patterns. This catches columns whose name doesn't
     hint at their content (e.g. "contact") and avoids over-trusting
     a name that turns out to hold nothing sensitive (e.g. an
     "email_template_id" foreign key).

Categories are aligned with what India's DPDP Act and GDPR both
single out for extra handling: standard PII, financial identifiers,
health data, biometric data, government-issued IDs, and "sensitive
personal data" categories like caste/religion/DOB where DPDP imposes
stricter consent expectations than plain contact info does.

`sensitivity_score` is a float in [0, 1], not a text label, so it can
be sorted/aggregated (e.g. by the data-quality and governance scoring
code) without a string comparison. A `risk_level` label is also
returned for display.
"""

import re


EMAIL_REGEX = re.compile(r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$')
PHONE_REGEX = re.compile(r'^[6-9]\d{9}$')
AADHAAR_REGEX = re.compile(r'^\d{4}\s?\d{4}\s?\d{4}$')
PAN_REGEX = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]{1}$')
IFSC_REGEX = re.compile(r'^[A-Z]{4}0[A-Z0-9]{6}$')
PASSPORT_REGEX = re.compile(r'^[A-PR-WYa-pr-wy][1-9]\d\s?\d{4}[1-9]$')
CREDIT_CARD_REGEX = re.compile(r'^\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,4}$')

# name_keyword -> (classification, dpdp_category, sensitivity_score,
#                   confidence, reason, recommendation, consent_required,
#                   value_pattern or None)
_NAME_RULES = [
    (["email"], "PII", "contact", 0.85, 0.90, "Column name indicates an email address", "Mask email values in non-production environments", True, EMAIL_REGEX),
    (["phone", "mobile", "contact_number"], "PII", "contact", 0.85, 0.85, "Column name indicates a phone number", "Tokenize phone numbers", True, PHONE_REGEX),
    (["aadhaar", "aadhar"], "SENSITIVE", "government_id", 0.98, 0.95, "Column name indicates an Aadhaar number", "Encrypt at rest and restrict access under DPDP", True, AADHAAR_REGEX),
    (["pan_number", "pan_no", "pancard"], "SENSITIVE", "government_id", 0.95, 0.90, "Column name indicates a PAN identifier", "Restrict access via RBAC", True, PAN_REGEX),
    (["passport"], "SENSITIVE", "government_id", 0.97, 0.90, "Column name indicates a passport number", "Restrict access via RBAC", True, PASSPORT_REGEX),
    (["voter_id", "voterid"], "SENSITIVE", "government_id", 0.95, 0.85, "Column name indicates a government-issued voter ID", "Restrict access via RBAC", True, None),
    (["ifsc"], "FINANCIAL", "financial", 0.60, 0.85, "Column name indicates a bank IFSC code", "Low standalone risk, but pair with account number implies financial identity", False, IFSC_REGEX),
    (["account_number", "acct_no", "bank_account"], "FINANCIAL", "financial", 0.95, 0.85, "Column name indicates a bank account number", "Encrypt at rest, restrict access", True, None),
    (["credit_card", "card_number", "debit_card"], "FINANCIAL", "financial", 0.98, 0.90, "Column name indicates a payment card number", "Never store unmasked; tokenize per PCI-DSS", True, CREDIT_CARD_REGEX),
    (["salary", "income", "ctc"], "FINANCIAL", "financial", 0.75, 0.75, "Column name indicates compensation data", "Restrict access to HR/finance roles", True, None),
    (["diagnosis", "medical", "health_condition", "prescription", "disease"], "SENSITIVE", "health", 0.98, 0.85, "Column name indicates health information", "Treat as sensitive personal data under DPDP; restrict and log access", True, None),
    (["biometric", "fingerprint", "retina", "face_id", "faceid"], "SENSITIVE", "biometric", 0.99, 0.85, "Column name indicates biometric data", "Highest-sensitivity category under DPDP; encrypt and strictly limit access", True, None),
    (["religion", "caste", "sexual_orientation", "political_affiliation"], "SENSITIVE", "sensitive_personal", 0.95, 0.80, "Column name indicates a DPDP-sensitive personal attribute", "Collect only with explicit, specific consent", True, None),
    (["date_of_birth", "dob", "birth_date"], "PII", "identity", 0.70, 0.85, "Column name indicates date of birth", "Combine-with-other-fields re-identification risk; restrict access", True, None),
    (["gender", "sex"], "PII", "identity", 0.40, 0.70, "Column name indicates gender", "Low standalone risk; consider aggregation before external sharing", False, None),
    (["password", "password_hash", "secret", "api_key", "token"], "SENSITIVE", "credentials", 0.99, 0.95, "Column name indicates a credential or secret", "Never expose via API responses; encrypt at rest", False, None),
    (["name", "full_name", "first_name", "last_name"], "PII", "identity", 0.55, 0.65, "Column name indicates a personal name", "Review manually - common word, moderate confidence", True, None),
    (["address", "street", "pincode", "postal_code", "zip"], "PII", "contact", 0.55, 0.60, "Column name indicates a physical address", "Review manually before external sharing", True, None),
]


def _match_ratio(pattern, values):
    """Fraction of non-empty sample values that match `pattern`."""

    checkable = [v for v in values if v not in (None, "")]

    if not checkable:
        return None

    matches = sum(1 for v in checkable if pattern.match(str(v).strip()))

    return matches / len(checkable)


def _risk_level(score: float) -> str:

    if score >= 0.8:
        return "HIGH"

    if score >= 0.5:
        return "MEDIUM"

    return "LOW"


def analyze_column(column_name: str, sample_values: list | None = None) -> dict:

    name = (column_name or "").lower()
    values = sample_values or []

    matched_rule = None

    for keywords, classification, dpdp_category, base_score, base_confidence, reason, recommendation, consent_required, pattern in _NAME_RULES:

        if any(keyword in name for keyword in keywords):
            matched_rule = {
                "classification": classification,
                "dpdp_category": dpdp_category,
                "sensitivity_score": base_score,
                "confidence": base_confidence,
                "reason": reason,
                "recommendation": recommendation,
                "consent_required": consent_required,
                "pattern": pattern,
            }
            break

    # No name signal at all: fall back to checking values against every
    # pattern we know, in case the column name is uninformative (e.g.
    # "field_12", "contact").
    if matched_rule is None:

        for keywords, classification, dpdp_category, base_score, base_confidence, reason, recommendation, consent_required, pattern in _NAME_RULES:

            if pattern is None:
                continue

            ratio = _match_ratio(pattern, values)

            if ratio is not None and ratio >= 0.6:

                score = min(base_score + 0.05, 1.0)

                return {
                    "classification": classification,
                    "dpdp_category": dpdp_category,
                    "sensitivity_score": round(score, 2),
                    "risk_level": _risk_level(score),
                    "confidence": round(min(base_confidence + 0.05, 0.99), 2),
                    "detection_reason": f"{reason} (detected from sampled values, not column name)",
                    "recommendation": recommendation,
                    "consent_required": consent_required,
                }

        return {
            "classification": "UNCLASSIFIED",
            "dpdp_category": None,
            "sensitivity_score": 0.05,
            "risk_level": "LOW",
            "confidence": 0.30,
            "detection_reason": "No sensitive naming pattern or value pattern detected",
            "recommendation": "No action required",
            "consent_required": False,
        }

    score = matched_rule["sensitivity_score"]
    confidence = matched_rule["confidence"]
    reason = matched_rule["reason"]

    # Name suggested something checkable - see if the actual values
    # back that up. Agreement raises confidence; disagreement lowers
    # it rather than silently trusting the name.
    if matched_rule["pattern"] is not None:

        ratio = _match_ratio(matched_rule["pattern"], values)

        if ratio is not None:

            if ratio >= 0.6:
                confidence = min(confidence + 0.10, 0.99)
                reason = f"{reason}; confirmed by sampled values"

            elif ratio <= 0.1:
                confidence = max(confidence - 0.30, 0.15)
                score = max(score - 0.20, 0.05)
                reason = f"{reason}; sampled values did not match the expected pattern, confidence lowered"

    return {
        "classification": matched_rule["classification"],
        "dpdp_category": matched_rule["dpdp_category"],
        "sensitivity_score": round(score, 2),
        "risk_level": _risk_level(score),
        "confidence": round(confidence, 2),
        "detection_reason": reason,
        "recommendation": matched_rule["recommendation"],
        "consent_required": matched_rule["consent_required"],
    }
