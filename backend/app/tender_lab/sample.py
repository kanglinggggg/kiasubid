from app.tender_lab.schemas import (
    CompanyContext,
    PricingInputs,
    StartupAnswers,
    TenderLabMode,
    TenderLabRequest,
)

SAMPLE_TENDER = """[Page 1]
The Digital Services Office seeks a supplier to implement and operate a managed cyber
monitoring service for community learning centres. The supplier shall provide onboarding,
monitoring, incident triage, monthly reporting and knowledge transfer.

[Page 4]
The service must provide 24x7 coverage. All administrator and remote support access must use
multi-factor authentication. Tenderers shall encrypt sensitive data at rest and in transit.
Production data and primary backups must be hosted in Singapore. The supplier must maintain
an incident response process and notify the agency of a confirmed security incident within
four hours. The supplier shall map its response to the IM8 control schedule supplied in Annex A.
The proposed cloud service provider must hold MTCS Level 2 certification or an accepted equivalent.

[Page 7]
The solution may require integrations with agency systems as required. Expected event volume
is TBC and should be sufficient for all participating centres. Final acceptance evidence will
be agreed where appropriate during implementation.

[Page 8]
Where the supplier is eligible for the Progressive Wage Mark, it shall hold the accreditation
throughout the contract period. Tenderers shall also report a measurable energy-consumption
baseline and environmental sustainability target for the managed service.

[Page 9]
Tenderers may subcontract bounded work packages only with the agency's prior written approval.

[Page 11]
The tender briefing will be held on 10 September 2026 at 10:00 SGT. Clarification questions
must be submitted by 12 September 2026 at 17:00 SGT. Tender submission closes on
18 September 2026 at 12:00 SGT.
"""


SAMPLE_PROPOSAL = """[Page 2]
Northstar Digital will operate a 24x7 monitoring roster with a named escalation manager.
The platform will run in the Singapore cloud region, including production data and backups.
Our incident response process uses a severity matrix and an incident commander, with agency
notification within four hours.

[Page 5]
The delivery plan covers discovery, onboarding, service validation and monthly reporting.
Acceptance artefacts will include a service report, escalation test and knowledge-transfer log.
"""


def sample_request(mode: TenderLabMode) -> TenderLabRequest:
    """Return a deterministic, clearly labelled sample for either workspace mode."""
    company = CompanyContext(
        name="Northstar Digital Pte. Ltd.",
        uen="202612345N",
        employee_count=18,
        annual_revenue_sgd=1_800_000,
        max_delivery_value_sgd=500_000,
        capabilities=[
            "Managed security monitoring",
            "Cloud delivery",
            "Incident response",
        ],
        certifications=["Supplier-declared ISO 27001"],
        entity_type="Exempt private company limited by shares",
        registration_status="Live Company",
        registration_date="2021-09-12",
        primary_ssic_code="62011",
        primary_ssic_description="Development of software and applications",
        paid_up_capital_sgd=250_000,
        profile_source_label="Declared company facts for the prepared workspace",
        source_type="SYNTHETIC_SAMPLE",
        verification_status="NOT_VERIFIED",
    )
    common = {
        "mode": mode,
        "tender_title": "Managed Cyber Monitoring for Community Learning Centres",
        "agency": "Digital Services Office (synthetic)",
        "source_label": "Prepared tender workspace",
        "source_type": "SYNTHETIC_SAMPLE",
        "tender_text": SAMPLE_TENDER,
        "proposal_text": SAMPLE_PROPOSAL,
        "contract_value_sgd": 450_000,
        "company": company,
    }
    if mode == "SME":
        return TenderLabRequest(
            **common,
            pricing=PricingInputs(
                estimated_cost_sgd=355_000,
                proposed_price_sgd=450_000,
                comparable_awards_sgd=[360_000, 390_000, 420_000, 445_000, 475_000],
                comparables_source="SYNTHETIC_SAMPLE",
                comparables_note=(
                    "Synthetic figures for sensitivity testing; they are not live GeBIZ data "
                    "and do not establish scope comparability."
                ),
            ),
        )
    return TenderLabRequest(
        **common,
        startup_answers=StartupAnswers(
            solution_summary=(
                "We give centre operators one shared view of security alerts and a clear way "
                "to escalate incidents, reducing the time spent checking separate tools."
            ),
            technical_architecture=(
                "A web dashboard receives normalised alerts through bounded connectors, keeps "
                "production data in the Singapore cloud region and separates operator access by role."
            ),
            delivery_approach=(
                "We will start with discovery, onboard a pilot group and expand after acceptance."
            ),
            operations_maintenance=(
                "The service lead will review monitoring alerts, coordinate support escalation and "
                "provide a monthly service report after go-live."
            ),
            security_approach="Data stays in Singapore and the team follows an incident process.",
            risk_management=(
                "The delivery lead will track integration-volume uncertainty and trigger a scope "
                "review if confirmed volumes exceed the stated assumption."
            ),
            team_strength="Two engineers have built monitoring integrations for a student pilot.",
            social_value="",
        ),
    )
