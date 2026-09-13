import re
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.tender_lab.policy_sources import (
    OFFICIAL_POLICY_RULES,
    POLICY_PACK_ID,
    POLICY_PACK_VERSION,
)
from app.tender_lab.schemas import (
    BriefClause,
    ClarificationQuestion,
    CoachFinding,
    Milestone,
    NextAction,
    OfficialPolicySource,
    PolicyCheck,
    PriceScenario,
    PricingAnalysis,
    ProposalSection,
    RemediationDraft,
    SourceReference,
    StartupCoach,
    StrategyRoute,
    TenderBrief,
    TenderLabRequest,
)

MAX_EXCERPT = 260


@dataclass(frozen=True)
class LocatedSentence:
    text: str
    location: str


@dataclass(frozen=True)
class ControlRule:
    id: str
    title: str
    tender_terms: tuple[str, ...]
    proposal_terms: tuple[str, ...]
    next_step: str


CONTROL_RULES = (
    ControlRule(
        "CTRL-MFA",
        "Multi-factor authentication",
        ("multi-factor", "multifactor", "mfa"),
        ("multi-factor", "multifactor", "mfa", "second factor"),
        "Add an implementation statement covering users, administrators and recovery controls.",
    ),
    ControlRule(
        "CTRL-ENCRYPTION",
        "Encryption at rest",
        ("encryption at rest", "encrypted at rest", "data at rest"),
        ("encryption at rest", "encrypted at rest", "aes-256", "kms"),
        "State the protected data classes, key ownership and evidence that will be supplied.",
    ),
    ControlRule(
        "CTRL-RESIDENCY",
        "Data residency",
        ("hosted in singapore", "data residency", "data localisation", "data localization"),
        (
            "hosted in singapore",
            "singapore region",
            "singapore cloud region",
            "data residency",
            "data localisation",
        ),
        "Name the hosting boundary and identify any support, backup or telemetry flows outside it.",
    ),
    ControlRule(
        "CTRL-INCIDENT",
        "Incident response",
        ("incident response", "security incident", "breach notification"),
        ("incident response", "breach notification", "severity matrix", "incident commander"),
        "Describe notification timing, severity ownership and the evidence used to close an incident.",
    ),
    ControlRule(
        "CTRL-COVERAGE",
        "Service coverage",
        ("24x7", "24 x 7", "round-the-clock", "twenty-four hours"),
        ("24x7", "24 x 7", "follow-the-sun", "round-the-clock", "shift roster"),
        "Show the operating roster, escalation path and coverage evidence.",
    ),
    ControlRule(
        "CTRL-CONTINUITY",
        "Service continuity",
        ("business continuity", "disaster recovery", "recovery time objective", "rto"),
        ("business continuity", "disaster recovery", "recovery time objective", "rto", "rpo"),
        "Provide recovery objectives, test cadence and the accountable recovery owner.",
    ),
)


REMEDIATION_EVIDENCE: dict[str, list[str]] = {
    "CTRL-MFA": [
        "Identity-provider policy or configuration export",
        "Administrator and recovery-account coverage evidence",
        "A dated access-control test result",
    ],
    "CTRL-ENCRYPTION": [
        "Data classification and storage inventory",
        "Encryption and key-management configuration evidence",
        "Key ownership and rotation record",
    ],
    "CTRL-RESIDENCY": [
        "Hosting-region architecture diagram",
        "Backup, telemetry and support data-flow inventory",
        "Provider region configuration evidence",
    ],
    "CTRL-INCIDENT": [
        "Incident response plan and severity matrix",
        "Notification workflow with accountable owners",
        "Most recent exercise or post-incident evidence",
    ],
    "CTRL-COVERAGE": [
        "Named operating roster and escalation path",
        "On-call coverage evidence for the required service window",
        "Service desk reporting sample",
    ],
    "CTRL-CONTINUITY": [
        "Approved continuity and disaster-recovery plan",
        "RTO and RPO mapped to the supplied tender clause",
        "Most recent recovery exercise result",
    ],
    "POLICY-IM8": [
        "The exact tender-supplied IM8 clause or control schedule",
        "Control-to-implementation mapping",
        "Current implementation and test evidence",
    ],
    "POLICY-MTCS": [
        "The tier or accepted equivalent stated in the tender",
        "Current provider certificate and validity period",
        "Service scope covered by the certificate",
    ],
    "POLICY-PW-MARK": [
        "Current PW Mark or PW Mark Plus accreditation",
        "Accreditation validity covering the contract period",
        "Subcontractor applicability and evidence, where required",
    ],
    "POLICY-SUSTAINABILITY": [
        "Tender-specific environmental measure",
        "Baseline, target and calculation method",
        "Named owner and reporting evidence",
    ],
    "POLICY-VALUE-FOR-MONEY": [
        "Published evaluation criteria and weightings",
        "Whole-life cost assumptions",
        "Evidence for quality, reliability and risk claims",
    ],
}


AMBIGUITY_MARKERS = (
    "as required",
    "where necessary",
    "where appropriate",
    "appropriate",
    "adequate",
    "sufficient",
    "reasonable",
    "to be confirmed",
    "tbc",
    "expected volume",
    "estimated volume",
    "may require",
)


DATE_PATTERN = re.compile(
    r"\b(?:"
    r"(?P<day>\d{1,2})\s+(?P<month>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
    r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+(?P<year>20\d{2})"
    r"|(?P<iso>20\d{2}-\d{2}-\d{2})"
    r")"
    r"(?:\s*(?:at|,)?\s*(?P<time>\d{1,2}(?::\d{2})?\s*(?:am|pm)?))?"
    r"(?:\s*(?:SGT|SST|Singapore time))?\b",
    re.IGNORECASE,
)


def _normalise_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clip(value: str, length: int = MAX_EXCERPT) -> str:
    cleaned = _normalise_space(value)
    return cleaned if len(cleaned) <= length else f"{cleaned[: length - 1].rstrip()}…"


def _sentences_with_locations(text: str) -> list[LocatedSentence]:
    page = "Supplied text"
    result: list[LocatedSentence] = []
    segments = re.split(r"(?=\[Page\s+\d+\])", text, flags=re.IGNORECASE)
    for segment in segments:
        page_match = re.match(r"\[Page\s+(\d+)\]", segment, flags=re.IGNORECASE)
        if page_match:
            page = f"Page {page_match.group(1)}"
            segment = segment[page_match.end() :]
        # A single newline is commonly only PDF/DOCX line wrapping. Keep it inside the
        # sentence so labels such as "Clarification questions\nmust be submitted ..."
        # retain their meaning. Known standalone headings become their own block, while
        # labels such as "Sustainability: 10 percent" stay attached to their criterion.
        segment = re.sub(
            r"(?im)^\s*(evaluation criteria|payment terms|deliverables|technical requirements|"
            r"functional requirements|contract conditions|terms and conditions|milestones|"
            r"project phases)\s*:?\s*$",
            r"\n\n\1:\n\n",
            segment,
        )
        for sentence in re.split(r"(?<=[.!?])\s+|\n{2,}", segment):
            cleaned = _normalise_space(sentence)
            if len(cleaned) >= 3:
                result.append(LocatedSentence(cleaned, page))
    if not result and _normalise_space(text):
        result.append(LocatedSentence(_normalise_space(text), page))
    return result


def _find_sentence(
    sentences: list[LocatedSentence], terms: tuple[str, ...] | list[str]
) -> LocatedSentence | None:
    for sentence in sentences:
        lowered = sentence.text.casefold()
        if any(term.casefold() in lowered for term in terms):
            return sentence
    return None


def _response_status(sentences: list[LocatedSentence], terms: tuple[str, ...]):
    """Conservative text evidence check, including contradictions anywhere in the draft.

    Never interpret a keyword alone as proof of implementation. This is intentionally
    a screen: future commitments, exceptions and negation are sent to human review.
    """
    matches = [s for s in sentences if any(re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", s.text, re.I) for t in terms)]
    if not matches:
        return "GAP", None
    for s in matches:
        if re.search(
            r"\b(open item|missing|unverified|not verified|evidence needed|provide and verify|"
            r"needs? (?:evidence|review|confirmation)|requires? (?:evidence|review|confirmation))\b",
            s.text,
            re.I,
        ):
            return "REVIEW", s
        if re.search(r"\b(not|never|cannot|can't|don't|doesn't|won't|without|lack\w*|except\w*|exclud\w*|no)\b", s.text, re.I):
            return "REVIEW", s
        if re.search(r"\b(plan\w*|propos\w*|intend\w*|will|would|may|might|pending|tbc|tbd)\b|\[[^]]+\]", s.text, re.I):
            return "REVIEW", s
    return "SUPPORTED", matches[0]


def _mandatory(text: str) -> bool:
    return bool(re.search(r"\b(must|shall|required|compulsory|mandatory)\b", text, re.I)) and not bool(
        re.search(r"\b(not required|not mandatory|not compulsory|need not|no requirement)\b", text, re.I)
    )


def _source(payload: TenderLabRequest, sentence: LocatedSentence) -> SourceReference:
    return SourceReference(
        source_label=payload.source_label,
        location=sentence.location,
        excerpt=_clip(sentence.text),
    )


def _remediation_draft(
    *,
    check_id: str,
    title: str,
    tender_source: SourceReference,
    next_step: str,
) -> RemediationDraft:
    evidence_needed = REMEDIATION_EVIDENCE.get(
        check_id,
        [
            "Tender-specific implementation evidence",
            "Named accountable owner",
            "Dated reviewer approval",
        ],
    )
    return RemediationDraft(
        title=f"Response scaffold — {title}",
        draft=(
            f"Requirement: {tender_source.excerpt}\n\n"
            f"Implementation: [Describe the control or delivery approach that is actually in place for {title}.]\n"
            "Scope: [Name the systems, users, locations or work packages covered.]\n"
            "Ownership: [Name the accountable role and operating team.]\n"
            "Verification: [Name the evidence, test method and latest verification date.]\n"
            "Exceptions: [State any exclusions, dependencies or open actions.]"
        ),
        placeholders=[
            "Actual implementation",
            "Covered scope",
            "Accountable owner",
            "Evidence and verification date",
            "Exceptions or dependencies",
        ],
        evidence_needed=evidence_needed,
        boundary=(
            f"Fill every placeholder from verified company facts before using this text. {next_step} "
            "Copying this scaffold does not establish compliance or change the proposal automatically."
        ),
    )


def build_brief(payload: TenderLabRequest) -> TenderBrief:
    sentences = _sentences_with_locations(payload.tender_text)
    objective = next(
        (
            item.text
            for item in sentences
            if any(
                term in item.text.casefold()
                for term in ("seeks", "invites", "procure", "engage", "appoint", "requires")
            )
        ),
        sentences[0].text,
    )
    mandatory = [
        _clip(item.text, 220)
        for item in sentences
        if _mandatory(item.text)
    ]
    outcomes = [
        _clip(item.text, 220)
        for item in sentences
        if re.search(r"\b(deliver|provide|implement|operate|maintain|support|develop)\w*\b", item.text, re.I)
    ]
    if not outcomes:
        outcomes = [_clip(item.text, 220) for item in sentences[:3]]
    short_objective = _clip(objective, 300)
    plain = f"{payload.agency} is seeking a supplier for {payload.tender_title}. "
    if mandatory:
        plain += f"The first review should verify {len(mandatory)} explicit mandatory signal"
        plain += "s" if len(mandatory) != 1 else ""
        plain += " before the team invests in a full response."
    else:
        plain += "No explicit mandatory wording was detected, so the original source still needs manual review."
    categories = {
        "Functions": r"\b(function\w*|feature\w*|system|platform|software|integrat\w*|api|architect\w*|scalab\w*)\b",
        "Deliverables": r"\b(deliver\w*|provide|implement\w*|develop\w*|report\w*|training|documentation)\b",
        "Evaluation criteria": r"\b(evaluat\w*|scor\w*|weight\w*|assessment criteria|selection criteria)\b",
        "Payment": r"\b(pay\w*|invoice\w*|deposit|bond|retention|financial milestone)\b",
        "Phases and milestones": r"\b(phase\w*|stage\w*|milestone\w*|uat|acceptance|go-live|deadline|submission|briefing|clarification|closing)\b",
        "Contract conditions": r"\b(liabilit\w*|indemn\w*|termination|warrant\w*|penalt\w*|intellectual property|maintenance|service level|contract period|subcontract\w*)\b",
    }
    clauses = []
    active_section = None
    for index, item in enumerate(sentences, 1):
        labels = [name for name, pattern in categories.items() if re.search(pattern, item.text, re.I)]
        heading = re.sub(r"^[\d.\s#-]+|[:\s]+$", "", item.text).casefold()
        section_names = {
            "evaluation criteria": "Evaluation criteria", "evaluation": "Evaluation criteria",
            "payment terms": "Payment", "payment": "Payment", "deliverables": "Deliverables",
            "technical requirements": "Functions", "functional requirements": "Functions",
            "contract conditions": "Contract conditions", "terms and conditions": "Contract conditions",
            "milestones": "Phases and milestones", "project phases": "Phases and milestones",
        }
        if heading in section_names:
            active_section = section_names[heading]
            continue
        if active_section and active_section not in labels:
            labels.append(active_section)
        if item.text.endswith(":") and heading not in section_names:
            active_section = None
        if _mandatory(item.text):
            labels.insert(0, "Mandatory requirements")
        if not labels:
            continue
        plain_text = item.text
        for pattern, replacement in (
            (r"\bshall\b", "must"), (r"\bprior to\b", "before"),
            (r"\bcommencement\b", "start"), (r"\bremuneration\b", "payment"),
            (r"\bpursuant to\b", "under"), (r"\bforthwith\b", "immediately"),
        ):
            plain_text = re.sub(pattern, replacement, plain_text, flags=re.I)
        clauses.append(BriefClause(
            id=f"REQ-{index:03}", categories=labels, plain_language=plain_text,
            source=SourceReference(source_label=payload.source_label, location=item.location, excerpt=item.text),
        ))
    return TenderBrief(
        objective=short_objective,
        plain_language_summary=plain,
        mandatory_signals=mandatory,
        requested_outcomes=outcomes,
        clauses=clauses,
        missing_sections=[label for label in categories if not any(label in c.categories for c in clauses)],
    )


def scan_policy_checks(payload: TenderLabRequest) -> list[PolicyCheck]:
    tender_sentences = _sentences_with_locations(payload.tender_text)
    proposal_text = re.sub(
        r"<!--\s*KIASUBID:OPEN_ITEMS_START\s*-->.*?<!--\s*KIASUBID:OPEN_ITEMS_END\s*-->",
        "",
        payload.proposal_text,
        flags=re.I | re.S,
    )
    proposal_text = re.split(
        r"(?im)^#{1,6}\s*Open Items for Human Review\s*$",
        proposal_text,
        maxsplit=1,
    )[0]
    proposal_sentences = _sentences_with_locations(proposal_text)
    findings: list[PolicyCheck] = []
    for rule in CONTROL_RULES:
        tender_match = _find_sentence(tender_sentences, rule.tender_terms)
        if tender_match is None:
            continue
        status, proposal_match = _response_status(proposal_sentences, rule.proposal_terms)
        is_mandatory = _mandatory(tender_match.text)
        findings.append(
            PolicyCheck(
                id=rule.id,
                title=rule.title,
                status=status,
                risk="MANDATORY" if is_mandatory else "REVIEW",
                rationale=(
                    "The draft contains a matching implementation statement. The reviewer must still confirm "
                    "that the statement and evidence satisfy the supplied tender wording."
                    if status == "SUPPORTED"
                    else "The draft mentions this control with a qualification, negation or future commitment. Check scope and implementation evidence; it is not established support."
                    if proposal_match
                    else "The supplied tender names this control, but no matching statement was found in the draft."
                ),
                tender_source=_source(payload, tender_match),
                proposal_evidence=_clip(proposal_match.text) if proposal_match else None,
                next_step=rule.next_step,
                remediation=(
                    _remediation_draft(
                        check_id=rule.id,
                        title=rule.title,
                        tender_source=_source(payload, tender_match),
                        next_step=rule.next_step,
                    )
                    if status != "SUPPORTED"
                    else None
                ),
            )
        )
    for rule in OFFICIAL_POLICY_RULES:
        tender_match = _find_sentence(tender_sentences, rule.tender_terms)
        if tender_match is None:
            continue
        proposal_match = _find_sentence(proposal_sentences, rule.proposal_terms)
        is_mandatory = _mandatory(tender_match.text)
        if proposal_match is None and is_mandatory:
            status = "GAP"
            rationale = (
                "The supplied tender explicitly triggers this named policy or standard, but no "
                "matching response statement was found in the proposal draft."
            )
        else:
            status = "REVIEW"
            rationale = (
                "Matching wording was found, but a reviewer must verify applicability and evidence "
                "against the exact tender clause."
                if proposal_match
                else "The tender names this policy context without a clear mandatory statement; applicability needs review."
            )
        findings.append(
            PolicyCheck(
                id=rule.id,
                title=rule.title,
                status=status,
                risk="MANDATORY" if is_mandatory else "REVIEW",
                rationale=rationale,
                tender_source=_source(payload, tender_match),
                proposal_evidence=_clip(proposal_match.text) if proposal_match else None,
                next_step=rule.next_step,
                pack_id=POLICY_PACK_ID,
                pack_version=POLICY_PACK_VERSION,
                basis="TENDER_TRIGGERED_OFFICIAL_CONTEXT",
                official_source=OfficialPolicySource(
                    publisher=rule.publisher,
                    title=rule.source_title,
                    url=rule.source_url,
                    reviewed_on="2026-09-12" if rule.id in {"POLICY-IM8", "POLICY-PWM"} else "2026-09-09",
                    supports=rule.supports,
                    limitation=rule.limitation,
                ),
                applicability_note=rule.applicability_note,
                remediation=(
                    _remediation_draft(
                        check_id=rule.id,
                        title=rule.title,
                        tender_source=_source(payload, tender_match),
                        next_step=rule.next_step,
                    )
                    if proposal_match is None
                    else None
                ),
            )
        )
    if not findings:
        anchor = tender_sentences[0]
        findings.append(
            PolicyCheck(
                id="CTRL-SOURCE-REVIEW",
                title="Tender-specific control review",
                status="REVIEW",
                risk="REVIEW",
                rationale=(
                    "No named baseline ICT control was detected by the deterministic policy pack. "
                    "This does not mean the tender has no policy obligations."
                ),
                tender_source=_source(payload, anchor),
                proposal_evidence=None,
                next_step="Inspect the supplied document and add a policy pack that matches its jurisdiction and category.",
            )
        )
    return findings


def _clarification_topic(sentence: str) -> tuple[str, str, str]:
    lowered = sentence.casefold()
    if any(term in lowered for term in ("volume", "capacity", "transaction", "user", "device")):
        return (
            "Demand volume is not measurable",
            "Please confirm the expected baseline, peak volume and growth assumption that bidders should price against.",
            "Changes infrastructure sizing, staffing and contingency cost.",
        )
    if any(term in lowered for term in ("retention", "data", "record", "log")):
        return (
            "Data obligation is underspecified",
            "Please confirm the required data classes, retention period, hosting boundary and deletion evidence.",
            "Changes storage architecture, compliance work and recurring cost.",
        )
    if any(term in lowered for term in ("integration", "api", "interface", "system")):
        return (
            "Integration boundary is unclear",
            "Please confirm the systems, interface specifications, test environment and acceptance owner in scope.",
            "Changes implementation effort, dependencies and delivery risk.",
        )
    if any(term in lowered for term in ("availability", "service level", "response time", "support")):
        return (
            "Service level is not measurable",
            "Please confirm the measurable target, measurement window, exclusions and service-credit basis.",
            "Changes staffing, monitoring design and commercial exposure.",
        )
    return (
        "Acceptance wording is ambiguous",
        "Please confirm the measurable scope, acceptance criteria and evidence expected for this requirement.",
        "May change scope, price or the evidence needed for acceptance.",
    )


def draft_clarifications(payload: TenderLabRequest) -> list[ClarificationQuestion]:
    questions: list[ClarificationQuestion] = []
    seen_topics: set[str] = set()
    for sentence in _sentences_with_locations(payload.tender_text):
        lowered = sentence.text.casefold()
        if not any(marker in lowered for marker in AMBIGUITY_MARKERS):
            continue
        issue, question, impact = _clarification_topic(sentence.text)
        if issue in seen_topics:
            continue
        seen_topics.add(issue)
        questions.append(
            ClarificationQuestion(
                id=f"CLAR-{len(questions) + 1:02d}",
                issue=issue,
                question=question,
                commercial_impact=impact,
                tender_source=_source(payload, sentence),
            )
        )
        if len(questions) == 6:
            break
    return questions


def _parse_date(match: re.Match[str]) -> datetime | None:
    raw_date = match.group("iso")
    if raw_date:
        date_value = datetime.strptime(raw_date, "%Y-%m-%d")
    else:
        month = match.group("month")[:3].title()
        raw = f"{match.group('day')} {month} {match.group('year')}"
        date_value = datetime.strptime(raw, "%d %b %Y")
    raw_time = _normalise_space(match.group("time") or "")
    if not raw_time:
        return date_value.replace(hour=9)
    for fmt in ("%H:%M", "%I:%M %p", "%I %p", "%H"):
        try:
            time_value = datetime.strptime(raw_time.upper(), fmt)
            return date_value.replace(hour=time_value.hour, minute=time_value.minute)
        except ValueError:
            continue
    return None


def _milestone_label(sentence: str) -> tuple[str, str]:
    lowered = sentence.casefold()
    if "clarif" in lowered or "question" in lowered:
        return "Clarification deadline", "HIGH"
    if any(term in lowered for term in ("submission", "closing", "close of tender", "tender closes")):
        return "Tender submission", "HIGH"
    if "briefing" in lowered or "site visit" in lowered:
        return "Tender briefing", "HIGH"
    if any(term in lowered for term in ("presentation", "demo", "interview")):
        return "Presentation or evaluation", "REVIEW"
    if any(term in lowered for term in ("bond", "guarantee", "deposit")):
        return "Financial instrument deadline", "REVIEW"
    if any(term in lowered for term in ("delivery", "go-live", "acceptance", "commencement", "phase", "uat")):
        return "Delivery milestone", "REVIEW"
    return "Tender milestone", "REVIEW"


def extract_milestones(payload: TenderLabRequest) -> list[Milestone]:
    milestones: list[Milestone] = []
    seen: set[tuple[str, str]] = set()
    for sentence in _sentences_with_locations(payload.tender_text):
        for match in DATE_PATTERN.finditer(sentence.text):
            parsed = _parse_date(match)
            if parsed is None:
                continue
            label, confidence = _milestone_label(sentence.text)
            if not match.group("time"):
                confidence = "REVIEW"
            key = (label, parsed.isoformat())
            if key in seen:
                continue
            seen.add(key)
            milestones.append(
                Milestone(
                    id=f"MILE-{len(milestones) + 1:02d}",
                    label=label,
                    starts_at=parsed.isoformat(timespec="minutes"),
                    confidence=confidence,  # type: ignore[arg-type]
                    tender_source=_source(payload, sentence),
                )
            )
    return sorted(milestones, key=lambda item: item.starts_at)


def analyse_pricing(payload: TenderLabRequest) -> PricingAnalysis | None:
    if payload.pricing is None:
        return None
    pricing = payload.pricing
    margin = pricing.proposed_price_sgd - pricing.estimated_cost_sgd
    margin_percent = margin / pricing.proposed_price_sgd * 100
    comparable_median = (
        float(statistics.median(pricing.comparable_awards_sgd))
        if pricing.comparable_awards_sgd
        else None
    )
    versus_median = (
        (pricing.proposed_price_sgd - comparable_median) / comparable_median * 100
        if comparable_median
        else None
    )
    if comparable_median is None:
        position = "No comparable award values were supplied. Only cost resilience can be calculated."
    elif versus_median < -10:
        position = "More than 10% below the supplied comparable median. Review underpricing and scope assumptions."
    elif versus_median > 10:
        position = "More than 10% above the supplied comparable median. Document the value and scope difference."
    else:
        position = "Within 10% of the supplied comparable median. Validate scope comparability before using it."

    scenarios: list[PriceScenario] = []
    for factor, label in ((0.90, "10% lower"), (1.0, "Current"), (1.10, "10% higher")):
        price = pricing.proposed_price_sgd * factor
        scenario_margin = price - pricing.estimated_cost_sgd
        scenarios.append(
            PriceScenario(
                label=label,
                price_sgd=round(price, 2),
                gross_margin_sgd=round(scenario_margin, 2),
                gross_margin_percent=round(scenario_margin / price * 100, 1),
                versus_median_percent=(
                    round((price - comparable_median) / comparable_median * 100, 1)
                    if comparable_median
                    else None
                ),
            )
        )
    return PricingAnalysis(
        proposed_price_sgd=round(pricing.proposed_price_sgd, 2),
        estimated_cost_sgd=round(pricing.estimated_cost_sgd, 2),
        gross_margin_sgd=round(margin, 2),
        gross_margin_percent=round(margin_percent, 1),
        comparable_count=len(pricing.comparable_awards_sgd),
        comparable_median_sgd=round(comparable_median, 2) if comparable_median else None,
        position=position,
        confidence=(
            "PUBLIC_AWARD_CONTEXT"
            if pricing.comparable_awards_sgd
            and pricing.comparables_source == "PUBLIC_AWARD_CONTEXT"
            else (
                "USER_SUPPLIED_COMPARABLES"
                if pricing.comparable_awards_sgd
                else "NO_COMPARABLES"
            )
        ),
        comparables_note=pricing.comparables_note,
        scenarios=scenarios,
        boundary=(
            "This is a deterministic cost and sensitivity calculation using values supplied in this workspace. "
            "It is not a win-probability model or a recommendation."
        ),
    )


def _direct_bid_route(
    payload: TenderLabRequest, policy_checks: list[PolicyCheck]
) -> StrategyRoute:
    mandatory_gaps = [
        item for item in policy_checks if item.status == "GAP" and item.risk == "MANDATORY"
    ]
    unresolved: list[str] = []
    status = "FEASIBLE"
    reasons: list[str] = []
    if (
        payload.contract_value_sgd
        and payload.company.max_delivery_value_sgd is not None
        and payload.contract_value_sgd > payload.company.max_delivery_value_sgd
    ):
        status = "BLOCKED"
        reasons.append("The supplied contract value exceeds the company's stated delivery-value limit.")
        unresolved.append("Authoritative financial or delivery capacity approval")
    elif mandatory_gaps:
        status = "RECOVERABLE"
        reasons.append(f"{len(mandatory_gaps)} tender-specified mandatory control gap(s) need closure.")
    elif not payload.proposal_text.strip():
        status = "UNCERTAIN"
        reasons.append("No proposal draft was supplied for evidence matching.")
        unresolved.append("Proposal evidence and implementation statements")
    else:
        reasons.append("No hard stop was found in the supplied capacity facts or tender-specific control scan.")
    if payload.company.max_delivery_value_sgd is None:
        unresolved.append("Company delivery-value approval")
        if status == "FEASIBLE":
            status = "UNCERTAIN"
    return StrategyRoute(
        id="ROUTE-DIRECT",
        title="Prepare a direct bid",
        status=status,  # type: ignore[arg-type]
        rationale=" ".join(reasons),
        unresolved_facts=unresolved,
        output=[
            "Close mandatory proposal gaps",
            "Confirm commercial capacity and delivery ownership",
            "Complete a human go or no-go review",
        ],
        basis=(
            "SYNTHETIC_SAMPLE"
            if payload.source_type == "SYNTHETIC_SAMPLE"
            else "USER_SUPPLIED_FACTS"
        ),
    )


def build_strategy_routes(
    payload: TenderLabRequest,
    policy_checks: list[PolicyCheck],
    clarifications: list[ClarificationQuestion],
) -> list[StrategyRoute]:
    direct = _direct_bid_route(payload, policy_checks)
    capabilities = payload.company.capabilities[:3] or ["A clearly bounded delivery work package"]
    routes = [direct]
    routes.append(
        StrategyRoute(
            id="ROUTE-SUBCONTRACT",
            title="Rescope as a delivery-partner package",
            status="UNCERTAIN",
            rationale=(
                "A partner route can preserve a specialised work package when a direct bid is too large, "
                "but no prime contractor demand, permission or eligibility is assumed."
            ),
            unresolved_facts=[
                "Tender permission for subcontracting",
                "Prime contractor demand and procurement process",
                "Partner qualification, commercials and availability",
            ],
            output=[
                f"Capability module: {capability}" for capability in capabilities
            ]
            + ["Evidence pack", "Scope boundary and hand-off assumptions"],
            basis=(
                "SYNTHETIC_SAMPLE"
                if payload.source_type == "SYNTHETIC_SAMPLE"
                else "USER_SUPPLIED_FACTS"
            ),
        )
    )
    if clarifications:
        routes.append(
            StrategyRoute(
                id="ROUTE-CLARIFY",
                title="Clarify before committing",
                status="UNCERTAIN",
                rationale=(
                    f"{len(clarifications)} ambiguity item(s) can materially change scope, cost or acceptance."
                ),
                unresolved_facts=[item.issue for item in clarifications[:4]],
                output=["Source-backed clarification draft", "Reprice and reassess after the response"],
                basis=(
                    "SYNTHETIC_SAMPLE"
                    if payload.source_type == "SYNTHETIC_SAMPLE"
                    else "USER_SUPPLIED_FACTS"
                ),
            )
        )
    return routes


def _answer_status(value: str) -> str:
    length = len(_normalise_space(value))
    if length >= 90:
        return "READY"
    if length >= 25:
        return "THIN"
    return "MISSING"


def build_startup_coach(
    payload: TenderLabRequest, policy_checks: list[PolicyCheck]
) -> StartupCoach | None:
    if payload.mode != "STARTUP":
        return None
    answers = payload.startup_answers
    values = {
        "Solution": answers.solution_summary if answers else "",
        "Architecture and scale": answers.technical_architecture if answers else "",
        "Delivery": answers.delivery_approach if answers else "",
        "Operations and maintenance": answers.operations_maintenance if answers else "",
        "Security": answers.security_approach if answers else "",
        "Risk management": answers.risk_management if answers else "",
        "Team": answers.team_strength if answers else "",
    }
    brief = build_brief(payload)
    social_criterion_found = any(
        "Evaluation criteria" in clause.categories
        and re.search(
            r"\b(sustainab\w*|environment\w*|social impact|social value|workforce|"
            r"skillsfuture|accessib\w*)\b",
            clause.source.excerpt,
            re.I,
        )
        for clause in brief.clauses
    )
    if social_criterion_found:
        values["Social value"] = answers.social_value if answers else ""
    prompts = {
        "Solution": "Explain the user problem, measurable outcome and why the proposed approach fits this tender.",
        "Architecture and scale": "Explain components, data flow, integrations and how unknown or expected volumes will be handled.",
        "Delivery": "Describe phases, milestones, acceptance evidence and who owns each hand-off.",
        "Operations and maintenance": "Describe post-go-live support, maintenance, monitoring, escalation and service evidence.",
        "Security": "Name concrete controls, operational evidence and the incident owner.",
        "Risk management": "Name tender-specific risks, owners, mitigations, triggers and unresolved dependencies.",
        "Team": "Map named roles and past proof to the work packages they will deliver.",
        "Social value": "State a credible local, workforce or sustainability outcome and how it will be measured.",
    }
    findings: list[CoachFinding] = []
    for area, value in values.items():
        status = _answer_status(value)
        critique = {
            "READY": "The answer is specific enough for a first draft, but supporting evidence still needs review.",
            "THIN": "The direction is present, but the answer lacks measurable delivery detail or proof.",
            "MISSING": "This section is not ready for evaluator review.",
        }[status]
        findings.append(
            CoachFinding(
                area=area,
                status=status,  # type: ignore[arg-type]
                critique=critique,
                next_prompt=prompts[area],
            )
        )

    sections = [
        ProposalSection(
            title="Executive summary",
            draft=(
                _normalise_space(values["Solution"])
                or "Draft the problem, proposed outcome and why the team is credible in three evidence-backed paragraphs."
            ),
            evidence_needed=["Tender outcome reference", "Measurable success metric"],
        ),
        ProposalSection(
            title="Technical architecture and scale",
            draft=(
                _normalise_space(values["Architecture and scale"])
                or "Describe components, data flow, integrations, scale assumptions and test evidence."
            ),
            evidence_needed=["Architecture diagram", "Integration inventory", "Scale assumptions and test evidence"],
        ),
        ProposalSection(
            title="Delivery and acceptance",
            draft=(
                _normalise_space(values["Delivery"])
                or "Define delivery phases, acceptance evidence, owners and dependencies."
            ),
            evidence_needed=["Milestone plan", "Acceptance artefact list", "Named delivery owner"],
        ),
        ProposalSection(
            title="Operations and maintenance",
            draft=(
                _normalise_space(values["Operations and maintenance"])
                or "Define support, maintenance, monitoring, escalation and reporting after go-live."
            ),
            evidence_needed=["Support model", "Maintenance plan", "Service-report example"],
        ),
        ProposalSection(
            title="Security and assurance",
            draft=(
                _normalise_space(values["Security"])
                or "Map each tender-specified control to an implementation statement and verifiable evidence."
            ),
            evidence_needed=[item.title for item in policy_checks if item.status != "SUPPORTED"],
        ),
        ProposalSection(
            title="Risk management",
            draft=(
                _normalise_space(values["Risk management"])
                or "Record delivery risks, owners, mitigations, triggers and assumptions needing clarification."
            ),
            evidence_needed=["Risk register", "Named risk owners", "Dependency and trigger log"],
        ),
        ProposalSection(
            title="Team and relevant proof",
            draft=(
                _normalise_space(values["Team"])
                or "Map roles, availability and relevant project evidence to the delivery plan."
            ),
            evidence_needed=["Role-to-work-package map", "Availability confirmation", "Comparable delivery evidence"],
        ),
    ]
    if social_criterion_found:
        sections.append(
            ProposalSection(
                title="Social value and measurement",
                draft=(
                    _normalise_space(values["Social value"])
                    or "Only include commitments the team can measure and contractually deliver."
                ),
                evidence_needed=[
                    "Published evaluation criterion",
                    "Baseline",
                    "Target",
                    "Measurement owner",
                ],
            )
        )
    rehearsal = [
        f"{finding.area}: {finding.next_prompt}"
        for finding in findings
        if finding.status != "READY"
    ][:5]
    rehearsal.extend(
        f"How will you prove {item.title.lower()} before acceptance?"
        for item in policy_checks
        if item.status == "GAP"
    )
    return StartupCoach(
        sections=sections,
        findings=findings,
        rehearsal_questions=rehearsal[:8],
        boundary=(
            "This is a structured first draft and critique based on user-supplied facts. "
            "It does not invent experience, certifications or policy commitments. Optional "
            "social-value coaching appears only when a matching published evaluation criterion "
            "is detected."
        ),
    )


def build_next_actions(
    policy_checks: list[PolicyCheck],
    clarifications: list[ClarificationQuestion],
    milestones: list[Milestone],
    pricing: PricingAnalysis | None,
    routes: list[StrategyRoute],
    startup_coach: StartupCoach | None,
) -> list[NextAction]:
    actions: list[NextAction] = []
    clarification_due = next(
        (item.starts_at for item in milestones if item.label == "Clarification deadline"), None
    )
    submission_due = next(
        (item.starts_at for item in milestones if item.label == "Tender submission"), None
    )
    for milestone in milestones:
        actions.append(NextAction(
            priority=2, title=f"Confirm and track {milestone.label.lower()}",
            reason="Verify the original date/time and assign a named owner. " + milestone.tender_source.excerpt,
            owner_role="Finance lead" if milestone.label == "Financial instrument deadline" else "Delivery lead" if milestone.label == "Delivery milestone" else "Bid manager",
            due_before=milestone.starts_at, source_ids=[milestone.id],
        ))
    for finding in policy_checks:
        if finding.status == "SUPPORTED":
            continue
        actions.append(
            NextAction(
                priority=1,
                title=f"Resolve {finding.title.lower()}",
                reason=finding.next_step,
                owner_role="Compliance or solution lead",
                due_before=submission_due,
                source_ids=[finding.id],
            )
        )
    if clarifications:
        actions.append(
            NextAction(
                priority=1,
                title="Review and submit clarification questions",
                reason=f"{len(clarifications)} ambiguity item(s) may change scope, price or acceptance.",
                owner_role="Bid manager",
                due_before=clarification_due,
                source_ids=[item.id for item in clarifications],
            )
        )
    if pricing and (pricing.gross_margin_percent < 10 or pricing.gross_margin_sgd < 0):
        actions.append(
            NextAction(
                priority=1,
                title="Revalidate the cost base and commercial floor",
                reason=f"Current gross margin is {pricing.gross_margin_percent:.1f}% before contingency.",
                owner_role="Commercial lead",
                due_before=submission_due,
                source_ids=["PRICING"],
            )
        )
    blocked_route = next((item for item in routes if item.id == "ROUTE-DIRECT" and item.status == "BLOCKED"), None)
    if blocked_route:
        actions.append(
            NextAction(
                priority=1,
                title="Choose a viable participation route",
                reason=blocked_route.rationale,
                owner_role="Business owner",
                due_before=submission_due,
                source_ids=[blocked_route.id],
            )
        )
    if startup_coach:
        for finding in startup_coach.findings:
            if finding.status == "READY":
                continue
            actions.append(
                NextAction(
                    priority=2,
                    title=f"Strengthen the {finding.area.lower()} section",
                    reason=finding.next_prompt,
                    owner_role="Proposal owner",
                    due_before=submission_due,
                    source_ids=[f"COACH-{finding.area.upper().replace(' ', '-')}"]
                )
            )
    if not actions:
        actions.append(
            NextAction(
                priority=3,
                title="Run the human go or no-go review",
                reason="No automatic hard stop was found, but commercial and tender interpretation remain human decisions.",
                owner_role="Bid owner",
                due_before=submission_due,
                source_ids=["HUMAN-REVIEW"],
            )
        )
    actions.sort(key=lambda item: (item.priority, item.due_before or "9999", item.title))
    return [item.model_copy(update={"priority": index}) for index, item in enumerate(actions, start=1)]


def _ics_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_calendar_ics(payload: TenderLabRequest, milestones: list[Milestone]) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//GeBIZ BidOps//Tender Lab//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_ics_escape(payload.tender_title)}",
    ]
    for item in milestones:
        start = datetime.fromisoformat(item.starts_at)
        end = start + timedelta(hours=1)
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{item.id.lower()}@gebiz-bidops.local",
                f"DTSTART;TZID=Asia/Singapore:{start.strftime('%Y%m%dT%H%M%S')}",
                f"DTEND;TZID=Asia/Singapore:{end.strftime('%Y%m%dT%H%M%S')}",
                f"SUMMARY:{_ics_escape(item.label)}",
                f"DESCRIPTION:{_ics_escape(item.tender_source.source_label + ' · ' + item.tender_source.excerpt)}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
