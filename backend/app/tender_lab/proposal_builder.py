import json
import re
from collections.abc import Callable
from typing import Literal

from pydantic import Field, model_validator

from app.config import Settings, settings
from app.llm.provider import JsonModelClient, ModelUnavailable, get_model_client
from app.tender_lab.agent_loop import AgentCallFailure, InvocationMeta, StructuredAgentRunner
from app.tender_lab.schemas import StrictModel, TenderLabRequest, TenderLabResponse
from app.tender_lab.workflow import run_tender_lab

ProposalAnswerKey = Literal[
    "solution_summary",
    "technical_architecture",
    "delivery_approach",
    "operations_maintenance",
    "security_approach",
    "risk_management",
    "team_strength",
    "social_value",
]
ProposalVerdict = Literal["STRONG", "NEEDS_DETAIL", "RISKY_CLAIM"]

REQUIRED_ANSWER_KEYS: tuple[ProposalAnswerKey, ...] = (
    "solution_summary",
    "technical_architecture",
    "delivery_approach",
    "operations_maintenance",
    "security_approach",
    "risk_management",
    "team_strength",
)
ANSWER_ORDER: tuple[ProposalAnswerKey, ...] = (*REQUIRED_ANSWER_KEYS, "social_value")

RISKY_CLAIM = re.compile(
    r"\b(?:guarantee(?:d|s)?|will win|100\s*%|fully compliant|zero risk|best in (?:the )?market|"
    r"certified compliant|automatic(?:ally)? approval)\b",
    re.I,
)
NUMBER_CLAIM = re.compile(r"(?<![A-Za-z0-9_])\d[\d,]*(?:\.\d+)?(?:\s*%)?(?![A-Za-z0-9_])")

class ProposalQuestion(StrictModel):
    id: str = Field(pattern=r"^Q-[A-Z-]+$")
    answer_key: ProposalAnswerKey
    section: str
    question: str
    why_it_matters: str
    answer_guidance: list[str] = Field(min_length=1, max_length=5)
    required: bool = True
    context_refs: list[str] = Field(default_factory=list, max_length=20)


class ProposalPlanRequest(StrictModel):
    tender: TenderLabRequest


class ProposalPlanResponse(StrictModel):
    questions: list[ProposalQuestion] = Field(min_length=5, max_length=8)
    mentor_intro: str
    boundary: str


class ProposalAnswerReviewRequest(StrictModel):
    tender: TenderLabRequest
    question_id: str = Field(pattern=r"^Q-[A-Z-]+$")
    answer: str = Field(min_length=2, max_length=3000)


class ProposalCritique(StrictModel):
    question_id: str = Field(pattern=r"^Q-[A-Z-]+$")
    verdict: ProposalVerdict
    mentor_feedback: str
    strengths: list[str] = Field(default_factory=list, max_length=4)
    gaps: list[str] = Field(default_factory=list, max_length=4)
    evidence_needed: list[str] = Field(default_factory=list, max_length=8)
    unsupported_claims: list[str] = Field(default_factory=list, max_length=8)
    formalized_answer: str = Field(min_length=2, max_length=4000)
    answer_quotes: list[str] = Field(min_length=1, max_length=6)
    needs_follow_up: bool
    follow_up_question: str | None = None

    @model_validator(mode="after")
    def consistent_follow_up(self) -> "ProposalCritique":
        if self.needs_follow_up != bool(self.follow_up_question):
            raise ValueError("follow_up_question must match needs_follow_up")
        return self


class ProposalExecution(StrictModel):
    mode: Literal["BEDROCK", "GROQ", "DETERMINISTIC_FALLBACK"]
    model_id: str | None = None
    attempts: int = Field(ge=0)
    duration_ms: float = Field(ge=0)
    detail: str


class ProposalAnswerReviewResponse(StrictModel):
    provider_state: Literal["LIVE", "FALLBACK"]
    critique: ProposalCritique
    execution: ProposalExecution
    fallback_reason: str | None = None
    boundary: str


class GroundedDraftSection(StrictModel):
    section_key: ProposalAnswerKey
    heading: str
    text: str = Field(min_length=2, max_length=6000)
    supporting_answer_keys: list[ProposalAnswerKey] = Field(min_length=1, max_length=3)
    context_refs: list[str] = Field(default_factory=list, max_length=20)


class ProposalDraftContent(StrictModel):
    title: str
    executive_summary: str = Field(min_length=2, max_length=6000)
    sections: list[GroundedDraftSection] = Field(min_length=5, max_length=8)
    open_items: list[str] = Field(default_factory=list, max_length=30)


class ProposalDraftRequest(StrictModel):
    tender: TenderLabRequest


class ProposalDraftResponse(StrictModel):
    provider_state: Literal["LIVE", "FALLBACK"]
    model_id: str | None = None
    title: str
    executive_summary: str
    sections: list[GroundedDraftSection]
    open_items: list[str]
    markdown: str
    review_notice: str
    execution: ProposalExecution
    fallback_reason: str | None = None
    boundary: str


def _normalise(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _questions(
    tender: TenderLabRequest, baseline: TenderLabResponse | None = None
) -> list[ProposalQuestion]:
    baseline = baseline or run_tender_lab(tender)
    gap_refs = [item.id for item in baseline.policy_checks if item.status != "SUPPORTED"]
    milestone_refs = [item.id for item in baseline.milestones]
    return [
        ProposalQuestion(
            id="Q-SOLUTION",
            answer_key="solution_summary",
            section="Solution and outcome",
            question=(
                f"What problem will your solution solve for {tender.agency}, what will users "
                "experience, and what outcome can the buyer verify?"
            ),
            why_it_matters="Evaluators need a direct line from the buyer's need to a testable outcome.",
            answer_guidance=[
                "Name the user or operational problem",
                "Describe the proposed experience in plain English",
                "Use a metric only if the team can evidence it",
            ],
            context_refs=["TENDER-OBJECTIVE"],
        ),
        ProposalQuestion(
            id="Q-ARCHITECTURE",
            answer_key="technical_architecture",
            section="Technical architecture",
            question=(
                "How will the main components, data flow and integrations work, and how will the "
                "design handle the tender's expected scale?"
            ),
            why_it_matters="A credible architecture makes delivery and assurance claims reviewable.",
            answer_guidance=[
                "Name only components the team actually plans to use",
                "Explain data boundaries and integration points",
                "State unknown volumes as assumptions, not facts",
            ],
            context_refs=["TENDER-OBJECTIVE", *gap_refs[:3]],
        ),
        ProposalQuestion(
            id="Q-DELIVERY",
            answer_key="delivery_approach",
            section="Delivery and acceptance",
            question=(
                "What are the delivery phases, who owns each hand-off, and what evidence will show "
                "that each phase has been accepted?"
            ),
            why_it_matters="A plan needs owners, dependencies and acceptance evidence—not activities alone.",
            answer_guidance=[
                "Describe phases and hand-offs",
                "Name accountable roles rather than inventing people",
                "Link acceptance evidence to the buyer's milestones",
            ],
            context_refs=milestone_refs[:6] or ["TENDER-OBJECTIVE"],
        ),
        ProposalQuestion(
            id="Q-OPERATIONS",
            answer_key="operations_maintenance",
            section="Operations and maintenance",
            question=(
                "After go-live, how will the team support, monitor and maintain the service, "
                "and what service evidence will the buyer receive?"
            ),
            why_it_matters=(
                "A credible proposal explains the operating model after implementation, not only the build."
            ),
            answer_guidance=[
                "Describe support hours and escalation without inventing an SLA",
                "Name maintenance, monitoring and reporting responsibilities",
                "Identify the service records or reports a reviewer can inspect",
            ],
            context_refs=["TENDER-OBJECTIVE", *milestone_refs[:4]],
        ),
        ProposalQuestion(
            id="Q-SECURITY",
            answer_key="security_approach",
            section="Security and privacy",
            question=(
                "Which stated security and privacy requirements can the team implement, how will "
                "they operate, and what proof will be available?"
            ),
            why_it_matters="A control statement without implementation and evidence is not submission proof.",
            answer_guidance=[
                "Address only requirements stated in the tender",
                "Separate current controls from planned controls",
                "Name the artefact a reviewer can inspect",
            ],
            context_refs=gap_refs[:8] or ["TENDER-OBJECTIVE"],
        ),
        ProposalQuestion(
            id="Q-RISK",
            answer_key="risk_management",
            section="Risk management",
            question=(
                "What are the most material delivery, dependency and adoption risks, who owns "
                "each response, and what trigger will cause the team to act?"
            ),
            why_it_matters=(
                "Evaluators need realistic risk ownership and mitigations rather than a claim of zero risk."
            ),
            answer_guidance=[
                "Name risks specific to this delivery",
                "Give each risk an owner, mitigation and trigger",
                "Separate confirmed dependencies from assumptions needing clarification",
            ],
            context_refs=["TENDER-OBJECTIVE", *gap_refs[:4]],
        ),
        ProposalQuestion(
            id="Q-TEAM",
            answer_key="team_strength",
            section="Team and governance",
            question=(
                "Which roles will deliver each work package, what relevant proof exists, and where "
                "does the team still need a partner or human decision?"
            ),
            why_it_matters="Evaluators need delivery capacity and evidence, not a generic team biography.",
            answer_guidance=[
                "Map roles to concrete work packages",
                "Mention experience only when evidence exists",
                "Expose capacity gaps instead of hiding them",
            ],
            context_refs=["FACT-COMPANY", "FACT-CAPABILITIES"],
        ),
        ProposalQuestion(
            id="Q-SOCIAL-VALUE",
            answer_key="social_value",
            section="Optional social value",
            question=(
                "Is there a local workforce, accessibility or sustainability outcome the team can "
                "contractually deliver and measure?"
            ),
            why_it_matters="Only tender-relevant, measurable commitments should enter the proposal.",
            answer_guidance=[
                "Confirm the tender actually evaluates this area",
                "State a baseline, measure and owner",
                "Skip this answer if there is no grounded commitment",
            ],
            required=False,
            context_refs=["TENDER-OBJECTIVE"],
        ),
    ]


def build_proposal_plan(request: ProposalPlanRequest) -> ProposalPlanResponse:
    return ProposalPlanResponse(
        questions=_questions(request.tender),
        mentor_intro=(
            "Explain the solution naturally. The mentor will challenge unsupported certainty, "
            "surface missing evidence and keep every draft section tied to a recorded answer."
        ),
        boundary=(
            "Questions are tailored from the supplied workspace. They do not confirm eligibility, "
            "compliance or evaluator preference."
        ),
    )


DETAIL_TERMS: dict[ProposalAnswerKey, tuple[str, ...]] = {
    "solution_summary": ("user", "buyer", "outcome", "measure", "problem", "workflow"),
    "technical_architecture": ("component", "data", "api", "integration", "scale", "cloud"),
    "delivery_approach": ("phase", "milestone", "owner", "accept", "handoff", "test"),
    "operations_maintenance": ("support", "maintain", "monitor", "service", "report", "escalat"),
    "security_approach": ("control", "encrypt", "access", "incident", "evidence", "audit"),
    "risk_management": ("risk", "owner", "mitigat", "trigger", "depend", "contingency"),
    "team_strength": ("role", "engineer", "lead", "owner", "experience", "available"),
    "social_value": ("baseline", "measure", "owner", "local", "accessib", "sustain"),
}

STRUCTURED_REVIEW_PROMPTS: dict[ProposalAnswerKey, str] = {
    "solution_summary": "Confirm the buyer need, user outcome and buyer-verifiable measure",
    "technical_architecture": "Confirm components, data boundaries, integrations, scale assumptions and architecture evidence",
    "delivery_approach": "Confirm phases, owners, hand-offs and acceptance artefacts",
    "operations_maintenance": "Confirm support hours, maintenance responsibilities, escalation and service evidence",
    "security_approach": "Confirm control scope, operation, owner and assurance evidence",
    "risk_management": "Confirm each risk, owner, mitigation, trigger and unresolved dependency",
    "team_strength": "Confirm role allocation, availability and evidence of relevant experience",
    "social_value": "Confirm the published criterion, achievable commitment, measure, cost and owner",
}


def _structured_fallback_answer(question: ProposalQuestion, answer: str) -> str:
    """Add a reviewable frame without inventing facts or silently filling gaps."""
    return (
        f"Recorded founder response: {answer}\n\n"
        f"Evidence check before use: [{STRUCTURED_REVIEW_PROMPTS[question.answer_key]}]."
    )


def _deterministic_critique(question: ProposalQuestion, answer: str) -> ProposalCritique:
    clean = _normalise(answer)
    lowered = clean.casefold()
    unsupported = list(dict.fromkeys(match.group(0) for match in RISKY_CLAIM.finditer(clean)))
    matched_terms = [term for term in DETAIL_TERMS[question.answer_key] if term in lowered]
    strengths: list[str] = []
    gaps: list[str] = []
    if len(clean) >= 80:
        strengths.append("The response has enough substance for a first-pass section.")
    else:
        gaps.append("Add concrete operating detail; the current answer is too short for review.")
    if matched_terms:
        strengths.append("The response includes section-relevant delivery language.")
    else:
        gaps.append("Connect the answer to the specific prompts and buyer outcome.")
    if not re.search(r"\b(?:evidence|report|log|test|record|certificate|diagram|runbook|metric)\b", lowered):
        gaps.append("Name the evidence or artefact a reviewer can inspect.")
    if unsupported:
        gaps.insert(0, "Replace absolute claims with bounded, evidence-backed wording.")
    gaps = list(dict.fromkeys(gaps))[:4]
    verdict: ProposalVerdict = (
        "RISKY_CLAIM" if unsupported else ("STRONG" if not gaps else "NEEDS_DETAIL")
    )
    follow_up = None
    if gaps:
        follow_up = (
            f"For {question.section.lower()}, {gaps[0][0].lower() + gaps[0][1:]} "
            "What can the team prove today?"
        )
    return ProposalCritique(
        question_id=question.id,
        verdict=verdict,
        mentor_feedback=(
            "Good first-pass answer. Keep the stated evidence available for human review."
            if verdict == "STRONG"
            else (
                "This answer makes an unsafe certainty claim. Revise it before it enters the draft."
                if verdict == "RISKY_CLAIM"
                else "The direction is useful, but the evaluator would still need more delivery detail."
            )
        ),
        strengths=strengths[:4],
        gaps=gaps,
        evidence_needed=[
            "A team-owned artefact supporting the implementation statement",
            *(["Evidence supporting any absolute or certification claim"] if unsupported else []),
        ],
        unsupported_claims=unsupported[:8],
        formalized_answer=_structured_fallback_answer(question, clean),
        answer_quotes=[clean[:500]],
        needs_follow_up=bool(follow_up),
        follow_up_question=follow_up,
    )


def _number_tokens(value: str) -> set[str]:
    return {re.sub(r"[\s,]", "", match.group(0)) for match in NUMBER_CLAIM.finditer(value)}


SAFE_DRAFT_TERMS = {
    "acceptance", "actual", "after", "against", "answer", "approach", "artefact",
    "available", "based", "before", "buyer", "check", "commitment", "confirm", "confirmed",
    "context", "control", "criteria", "criterion", "data", "delivery", "dependency", "describe",
    "draft", "each", "evidence", "founder", "from", "governance", "grounded", "human",
    "identify", "implementation", "information", "integration", "maintenance", "management",
    "measure", "missing", "needed", "needs", "open", "operating", "operations", "outcome",
    "owner", "privacy", "proof", "proposal", "proposed", "provided", "recorded", "relevant",
    "requirement", "response", "review", "risk", "risks", "scope", "section", "security",
    "service", "solution", "source", "state", "structured", "submission", "support", "supported",
    "team", "tender", "unresolved", "user", "value", "verification", "verify", "wording",
}


def _novel_content_terms(value: str, source: str) -> set[str]:
    """Find substantive vocabulary absent from the tender and recorded answers.

    Bracketed text is an explicit placeholder and is excluded. If a live rewrite adds
    a technology, credential or factual concept, validation fails closed to the
    deterministic scaffold.
    """
    without_placeholders = re.sub(r"\[[^]]*]", " ", value)
    terms = set(re.findall(r"\b[a-z][a-z0-9.+/-]{3,}\b", without_placeholders.casefold()))
    source_terms = set(re.findall(r"\b[a-z][a-z0-9.+/-]{3,}\b", source.casefold()))
    return terms - source_terms - SAFE_DRAFT_TERMS


def _validate_live_critique(
    critique: ProposalCritique, *, question: ProposalQuestion, answer: str, tender_text: str
) -> None:
    if critique.question_id != question.id:
        raise ValueError("mentor changed the question identifier")
    clean_answer = _normalise(answer)
    if clean_answer not in _normalise(critique.formalized_answer):
        raise ValueError("mentor rewrite omitted the recorded founder answer")
    if any(_normalise(quote) not in clean_answer for quote in critique.answer_quotes):
        raise ValueError("mentor quoted wording that was not in the supplied answer")
    allowed_numbers = _number_tokens(answer + "\n" + tender_text)
    introduced = _number_tokens(critique.formalized_answer) - allowed_numbers
    if introduced:
        raise ValueError("mentor introduced a numeric claim absent from supplied material")
    if RISKY_CLAIM.search(critique.formalized_answer) and not RISKY_CLAIM.search(answer):
        raise ValueError("mentor introduced an unsupported certainty claim")
    if _novel_content_terms(critique.formalized_answer, answer + "\n" + tender_text):
        raise ValueError("mentor introduced factual vocabulary absent from supplied material")


def _execution(meta: InvocationMeta | None, detail: str) -> ProposalExecution:
    if meta is None:
        return ProposalExecution(
            mode="DETERMINISTIC_FALLBACK",
            attempts=0,
            duration_ms=0,
            detail=detail,
        )
    return ProposalExecution(
        mode=meta.mode,  # type: ignore[arg-type]
        model_id=meta.model_id,
        attempts=meta.attempts,
        duration_ms=meta.duration_ms,
        detail=detail,
    )


def _safe_fallback_reason(exc: AgentCallFailure | ModelUnavailable | ValueError) -> str:
    """Return a useful UI reason without leaking provider or credential diagnostics."""
    if isinstance(exc, ModelUnavailable):
        return "The configured language-model provider was unavailable."
    if isinstance(exc, AgentCallFailure):
        return "The configured language-model request could not be completed or validated."
    return "The live language-model output did not pass the grounding checks."


def review_proposal_answer(
    request: ProposalAnswerReviewRequest,
    *,
    app_settings: Settings = settings,
    client_factory: Callable[[Settings], JsonModelClient] = get_model_client,
) -> ProposalAnswerReviewResponse:
    question = next(
        (item for item in _questions(request.tender) if item.id == request.question_id), None
    )
    if question is None:
        raise LookupError("Proposal mentor question not found.")
    fallback = _deterministic_critique(question, request.answer)
    if not app_settings.interpretation_configured:
        return ProposalAnswerReviewResponse(
            provider_state="FALLBACK",
            critique=fallback,
            execution=_execution(None, "Used the deterministic mentor because no model is configured."),
            fallback_reason="The configured language-model provider is not available.",
            boundary="The mentor critiques wording; it does not validate the underlying claim.",
        )
    try:
        runner = StructuredAgentRunner(client_factory(app_settings), app_settings)
        prompt = f"""You are the Proposal Mentor Agent. Critique one founder answer and rewrite it
as restrained procurement language. Preserve meaning. Do not invent facts. answer_quotes must be
exact substrings of FOUNDER ANSWER. If evidence is missing, list it and ask one useful follow-up.

QUESTION:
{json.dumps(question.model_dump(mode='json'), ensure_ascii=False)}

FOUNDER ANSWER:
{request.answer}

SUPPLIED TENDER TEXT (reference only):
{request.tender.tender_text[:30_000]}
"""
        critique, meta = runner.invoke(
            prompt=prompt,
            schema_name="proposal_mentor_critique",
            output_model=ProposalCritique,
            validator=lambda value: _validate_live_critique(
                value,
                question=question,
                answer=request.answer,
                tender_text=request.tender.tender_text,
            ),
        )
        return ProposalAnswerReviewResponse(
            provider_state="LIVE",
            critique=critique,
            execution=_execution(meta, "The live mentor critiqued and grounded one founder answer."),
            boundary="The mentor critiques wording; it does not validate the underlying claim.",
        )
    except (AgentCallFailure, ModelUnavailable, ValueError) as exc:
        return ProposalAnswerReviewResponse(
            provider_state="FALLBACK",
            critique=fallback,
            execution=_execution(None, "Live mentor failed safely; deterministic critique continued."),
            fallback_reason=_safe_fallback_reason(exc),
            boundary="The mentor critiques wording; it does not validate the underlying claim.",
        )


SECTION_HEADINGS: dict[ProposalAnswerKey, str] = {
    "solution_summary": "Proposed Solution and Outcomes",
    "technical_architecture": "Technical Architecture",
    "delivery_approach": "Delivery and Acceptance",
    "operations_maintenance": "Operations and Maintenance",
    "security_approach": "Security and Privacy",
    "risk_management": "Risk Management",
    "team_strength": "Team and Governance",
    "social_value": "Social Value",
}


def _answer_map(tender: TenderLabRequest) -> dict[ProposalAnswerKey, str]:
    answers = tender.startup_answers
    if answers is None:
        return {key: "" for key in ANSWER_ORDER}
    return {key: _normalise(getattr(answers, key)) for key in ANSWER_ORDER}


def _open_items(
    tender: TenderLabRequest,
    answer_map: dict[ProposalAnswerKey, str],
    *,
    baseline: TenderLabResponse,
    questions: list[ProposalQuestion],
) -> list[str]:
    items = [
        f"Provide and verify evidence for {check.title}."
        for check in baseline.policy_checks
        if check.status != "SUPPORTED"
    ]
    questions_by_key = {item.answer_key: item for item in questions}
    for key in REQUIRED_ANSWER_KEYS:
        question = questions_by_key[key]
        critique = _deterministic_critique(question, answer_map[key])
        items.extend(critique.gaps[:1])
        if critique.unsupported_claims:
            items.append(
                f"Human review must qualify unsupported wording in {SECTION_HEADINGS[key]}: "
                + ", ".join(critique.unsupported_claims)
            )
    return list(dict.fromkeys(items))[:30]


def _fallback_draft(tender: TenderLabRequest) -> ProposalDraftContent:
    answers = _answer_map(tender)
    baseline = run_tender_lab(tender)
    questions = _questions(tender, baseline)
    questions_by_key = {item.answer_key: item for item in questions}
    sections = [
        GroundedDraftSection(
            section_key=key,
            heading=SECTION_HEADINGS[key],
            text=answers[key],
            supporting_answer_keys=[key],
            context_refs=questions_by_key[key].context_refs,
        )
        for key in ANSWER_ORDER
        if answers[key]
    ]
    return ProposalDraftContent(
        title=f"{tender.tender_title} — Supplier Response Draft",
        executive_summary=answers["solution_summary"],
        sections=sections,
        open_items=_open_items(
            tender,
            answers,
            baseline=baseline,
            questions=questions,
        ),
    )


def _validate_draft_content(
    content: ProposalDraftContent,
    *,
    tender: TenderLabRequest,
    answers: dict[ProposalAnswerKey, str],
) -> None:
    section_keys = [section.section_key for section in content.sections]
    if len(section_keys) != len(set(section_keys)):
        raise ValueError("proposal draft contains duplicate sections")
    if not set(REQUIRED_ANSWER_KEYS).issubset(section_keys):
        raise ValueError("proposal draft omitted a required interview section")
    allowed_keys = {key for key, value in answers.items() if value}
    allowed_numbers = _number_tokens(tender.tender_text + "\n" + "\n".join(answers.values()))
    text_parts = [content.executive_summary, *[item.text for item in content.sections]]
    if _number_tokens("\n".join(text_parts)) - allowed_numbers:
        raise ValueError("proposal draft introduced a numeric claim absent from supplied material")
    if any(RISKY_CLAIM.search(part) for part in text_parts):
        raise ValueError("proposal draft retained an unsafe certainty claim")
    source_material = tender.tender_text + "\n" + "\n".join(answers.values())
    if _novel_content_terms("\n".join(text_parts), source_material):
        raise ValueError("proposal draft introduced factual vocabulary absent from supplied material")
    if _normalise(answers["solution_summary"]) not in _normalise(content.executive_summary):
        raise ValueError("proposal executive summary is not anchored to the recorded solution answer")
    for section in content.sections:
        if not set(section.supporting_answer_keys).issubset(allowed_keys):
            raise ValueError("proposal section cites an empty or unknown founder answer")
        if not any(
            _normalise(answers[key]) in _normalise(section.text)
            for key in section.supporting_answer_keys
        ):
            raise ValueError("proposal section is not anchored to its recorded founder answer")


def _render_markdown(content: ProposalDraftContent) -> str:
    lines = [
        f"# {content.title}",
        "",
        "> AI-assisted preparation draft. Verify every claim, source and commitment before submission.",
        "",
        "## Executive Summary",
        "",
        content.executive_summary,
        "",
    ]
    for section in content.sections:
        lines.extend([f"## {section.heading}", "", section.text, ""])
    if content.open_items:
        lines.extend(["<!-- KIASUBID:OPEN_ITEMS_START -->", "## Open Items for Human Review", ""])
        lines.extend(f"- {item}" for item in content.open_items)
        lines.extend(["", "<!-- KIASUBID:OPEN_ITEMS_END -->", ""])
    return "\n".join(lines).strip() + "\n"


def generate_proposal_draft(
    request: ProposalDraftRequest,
    *,
    app_settings: Settings = settings,
    client_factory: Callable[[Settings], JsonModelClient] = get_model_client,
) -> ProposalDraftResponse:
    answers = _answer_map(request.tender)
    missing = [SECTION_HEADINGS[key] for key in REQUIRED_ANSWER_KEYS if not answers[key]]
    if missing:
        raise ValueError("Answer the required mentor questions first: " + ", ".join(missing))
    risky = [SECTION_HEADINGS[key] for key, answer in answers.items() if RISKY_CLAIM.search(answer)]
    if risky:
        raise ValueError(
            "Revise unsupported certainty claims before drafting: " + ", ".join(risky)
        )
    fallback = _fallback_draft(request.tender)
    content = fallback
    meta: InvocationMeta | None = None
    reason: str | None = None
    provider_state: Literal["LIVE", "FALLBACK"] = "FALLBACK"
    if app_settings.interpretation_configured:
        try:
            runner = StructuredAgentRunner(client_factory(app_settings), app_settings)
            plan = build_proposal_plan(ProposalPlanRequest(tender=request.tender))
            prompt = f"""You are the Proposal Drafting Agent. Turn recorded founder answers into
a restrained, coherent supplier response. Do not add facts. Every section must cite one or more
supporting_answer_keys. Keep uncertain or missing proof in open_items. Do not claim compliance,
certification, award probability or guaranteed outcomes.

TENDER CONTEXT:
{request.tender.tender_text[:35_000]}

QUESTION PLAN:
{json.dumps([item.model_dump(mode='json') for item in plan.questions], ensure_ascii=False)}

RECORDED ANSWERS:
{json.dumps(answers, ensure_ascii=False)}
"""
            content, meta = runner.invoke(
                prompt=prompt,
                schema_name="grounded_proposal_draft",
                output_model=ProposalDraftContent,
                validator=lambda value: _validate_draft_content(
                    value, tender=request.tender, answers=answers
                ),
            )
            provider_state = "LIVE"
        except (AgentCallFailure, ModelUnavailable, ValueError) as exc:
            reason = _safe_fallback_reason(exc)
    else:
        reason = "The configured language-model provider is not available."
    return ProposalDraftResponse(
        provider_state=provider_state,
        model_id=meta.model_id if meta else None,
        title=content.title,
        executive_summary=content.executive_summary,
        sections=content.sections,
        open_items=content.open_items,
        markdown=_render_markdown(content),
        review_notice=(
            "AI-assisted preparation draft. The supplier must verify every claim, requirement, "
            "price, date and commitment before submission."
        ),
        execution=_execution(
            meta,
            (
                "The live drafting agent produced a grounded response."
                if meta
                else "Used recorded answers directly so the workflow could continue safely."
            ),
        ),
        fallback_reason=reason,
        boundary=(
            "The generated draft is preparation material. It does not establish compliance, "
            "eligibility, delivery capacity or buyer acceptance."
        ),
    )
