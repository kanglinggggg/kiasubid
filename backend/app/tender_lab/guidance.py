"""Lexical retrieval over a small, versioned first-party guidance summary corpus.

Summaries are NOT verbatim legal text, nor a live policy crawler. A query must be
grounded in the supplied tender; the tender determines applicability, not this index.
"""
import re

from app.tender_lab.policy_sources import OFFICIAL_POLICY_RULES
from app.tender_lab.schemas import RetrievedGuidance

REVIEWED_ON = "2026-09-12"
CONTROL_PASSAGES = (
    ("POLICY-AC2", "Access control — AC-2", ("mfa", "multi-factor", "multifactor", "privileged accounts"),
     "https://info.standards.tech.gov.sg/control-catalog/cybersecurity/ac/",
     "GovTech's AC-2 control calls for privileged-account login to use MFA. Its implementation recommendations distinguish authentication factors and discuss additional checks for privileged actions.",
     "Confirm the tender's applicable control profile, covered accounts and evidence. A sentence about MFA is not an implementation test."),
    ("POLICY-DP", "Data protection controls", ("encryption", "encrypted", "data protection", "personal data"),
     "https://info.standards.tech.gov.sg/control-catalog/cybersecurity/dp/",
     "The public data-protection catalogue describes controls for protecting data. It separates control statements, implementation recommendations and risk context.",
     "Use the exact applicable controls and parameters from the tender. This summary does not set a universal hosting or encryption requirement."),
)


def retrieve_guidance(tender_text: str) -> list[RetrievedGuidance]:
    def matched(terms):
        return [term for term in terms if re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", tender_text, re.I)]

    passages = []
    for rule in OFFICIAL_POLICY_RULES:
        terms = matched(rule.tender_terms)
        if terms:
            passages.append(RetrievedGuidance(
                id=rule.id, title=rule.source_title, publisher=rule.publisher,
                url=rule.source_url, reviewed_on=REVIEWED_ON if rule.id in {"POLICY-IM8", "POLICY-PWM"} else "2026-09-09", passage=rule.supports,
                matched_terms=terms, limitation=rule.limitation,
            ))
    for id_, title, keywords, url, passage, limitation in CONTROL_PASSAGES:
        terms = matched(keywords)
        if terms:
            passages.append(RetrievedGuidance(
                id=id_, title=title, publisher="Government Technology Agency of Singapore",
                url=url, reviewed_on=REVIEWED_ON, passage=passage,
                matched_terms=terms, limitation=limitation,
            ))
    return passages
