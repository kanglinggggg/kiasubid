from dataclasses import dataclass


@dataclass(frozen=True)
class OfficialPolicyRule:
    id: str
    title: str
    tender_terms: tuple[str, ...]
    proposal_terms: tuple[str, ...]
    next_step: str
    publisher: str
    source_title: str
    source_url: str
    supports: str
    limitation: str
    applicability_note: str
    context_only: bool = False


# This is a small, versioned registry of public first-party sources. It deliberately does not
# reproduce or pretend to possess non-public policy manuals. A tender clause is always the source
# of applicability; these pages only provide public policy context for a reviewer.
OFFICIAL_POLICY_RULES = (
    OfficialPolicyRule(
        id="POLICY-IM8",
        title="IM8 clause mapping",
        tender_terms=("im8", "instruction manual 8"),
        proposal_terms=("im8", "instruction manual 8"),
        next_step=(
            "Map the response to the exact IM8 clause or control schedule supplied with this tender, "
            "then attach implementation evidence for human review."
        ),
        publisher="Government Technology Agency of Singapore",
        source_title="CloudSCAPE overview",
        source_url=(
            "https://v2.developer.tech.gov.sg/products/categories/cybersecurity/"
            "cloudscape/overview"
        ),
        supports=(
            "GovTech publicly describes automated compliance monitoring for GCC workloads against IM8."
        ),
        limitation=(
            "The public page is not the IM8 control text and cannot establish tender compliance. "
            "The exact tender-supplied clause remains authoritative."
        ),
        applicability_note="Only triggered when the supplied tender explicitly names IM8.",
        context_only=True,
    ),
    OfficialPolicyRule(
        id="POLICY-MTCS",
        title="MTCS requirement",
        tender_terms=("multi-tier cloud security", "multi tier cloud security", "mtcs"),
        proposal_terms=("multi-tier cloud security", "multi tier cloud security", "mtcs"),
        next_step=(
            "Confirm the required MTCS tier or accepted equivalent in the tender and attach current "
            "provider certification evidence."
        ),
        publisher="Cyber Security Agency of Singapore",
        source_title="Cloud Security for Organisations",
        source_url=(
            "https://www.csa.gov.sg/our-programmes/support-for-enterprises/"
            "sg-cyber-safe-programme/cloud-security-for-organisations/"
        ),
        supports=(
            "CSA's public cloud-security guidance identifies MTCS as a Singapore cloud-security "
            "standard that organisations may consider when assessing providers."
        ),
        limitation=(
            "MTCS is not automatically mandatory for every procurement. The supplied tender must "
            "state the tier, evidence and applicability."
        ),
        applicability_note="Only triggered when the supplied tender explicitly names MTCS.",
    ),
    OfficialPolicyRule(
        id="POLICY-PW-MARK",
        title="Progressive Wage Mark",
        tender_terms=("progressive wage mark", "pw mark", "pw mark plus"),
        proposal_terms=("progressive wage mark", "pw mark", "pw mark plus"),
        next_step=(
            "Confirm whether the supplier is eligible for the PW Mark requirement and attach current "
            "accreditation covering the contract period."
        ),
        publisher="Ministry of Manpower Singapore",
        source_title="Progressive Wage Mark",
        source_url=(
            "https://www.mom.gov.sg/employment-practices/progressive-wage-model/"
            "progressive-wage-mark"
        ),
        supports=(
            "MOM states that eligible firms awarded Government contracts for tenders called from "
            "1 March 2023 must hold the PW Mark for the contract period; the requirement also applies "
            "to supporting subcontractors."
        ),
        limitation=(
            "Eligibility depends on the firm's workforce and the procurement. A text match is not "
            "proof of accreditation."
        ),
        applicability_note="Only triggered when the supplied tender explicitly names the PW Mark.",
    ),
    OfficialPolicyRule(
        id="POLICY-SUSTAINABILITY",
        title="Environmental sustainability requirement",
        tender_terms=(
            "environmental sustainability",
            "green procurement",
            "carbon emissions",
            "energy efficiency",
        ),
        proposal_terms=(
            "environmental sustainability",
            "carbon emissions",
            "energy efficiency",
            "energy consumption",
            "emissions baseline",
        ),
        next_step=(
            "Respond to the tender's stated sustainability measure with a baseline, target, method "
            "and accountable owner; do not invent a generic score."
        ),
        publisher="Ministry of Finance Singapore",
        source_title=(
            "Timeline to Include Environmental Sustainability Requirements and Evaluation Criteria "
            "into All Government Procurements"
        ),
        source_url=(
            "https://www.mof.gov.sg/news-resources/newsroom/"
            "timeline-to-include-environmental-sustainability-requirements-and-evaluation-criteria-"
            "into-all-government-procurements/"
        ),
        supports=(
            "MOF states that environmental sustainability considerations are being progressively "
            "extended across Government procurement, with an aim to cover all procurement by 2028."
        ),
        limitation=(
            "The source does not create one universal score or requirement. The tender's own "
            "evaluation criteria remain authoritative."
        ),
        applicability_note=(
            "Only triggered when the supplied tender contains an environmental requirement."
        ),
    ),
    OfficialPolicyRule(
        id="POLICY-VALUE-FOR-MONEY",
        title="Price-quality evaluation",
        tender_terms=("price-quality", "price quality", "pqm", "value for money"),
        proposal_terms=("price-quality", "price quality", "value for money", "whole-life cost"),
        next_step=(
            "Use the evaluation criteria and weightings published in this tender; explain quality, "
            "risk and whole-life value without assuming a hidden agency preference."
        ),
        publisher="Ministry of Finance Singapore",
        source_title="Government procurement",
        source_url="https://www.mof.gov.sg/policies/government-procurement/overview/",
        supports=(
            "MOF describes value for money as considering quality, reliability, risk, timeliness, "
            "long-term costs and wider outcomes rather than lowest price alone."
        ),
        limitation=(
            "The public principle does not reveal a tender's scoring weights. Use only weightings "
            "published in the supplied tender."
        ),
        applicability_note=(
            "Only triggered when the supplied tender names a price-quality or value-for-money method."
        ),
        context_only=True,
    ),
)


POLICY_PACK_ID = "SG-OFFICIAL-PUBLIC-CONTEXT"
POLICY_PACK_VERSION = "2026-09-09"
