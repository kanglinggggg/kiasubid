from app.main import app
from app.tender_lab.change_simulator import ChangeSimulationRequest, simulate_tender_change
from app.tender_lab.sample import sample_request
from fastapi.testclient import TestClient


def _baseline():
    return sample_request("SME").model_copy(
        update={
            "tender_title": "Managed support service",
            "source_label": "Baseline tender.pdf",
            "tender_text": (
                "[Page 1]\nThe agency seeks a supplier to provide a managed support service. "
                "The supplier must provide 24x7 coverage. Tender submission closes on "
                "18 September 2026 at 12:00 SGT."
            ),
            "proposal_text": (
                "[Page 2]\nWe provide a named 24x7 shift roster with an escalation owner."
            ),
        }
    )


def _change_request() -> ChangeSimulationRequest:
    return ChangeSimulationRequest(
        tender=_baseline(),
        source_label="Corrigendum 3.pdf",
        amendment_text=(
            "[Page 2]\nThe supplier must maintain a disaster recovery capability with a "
            "four-hour recovery time objective. The service adds three locations, but expected "
            "event volume remains TBC. Tender submission closes on 20 September 2026 at 12:00 SGT."
        ),
    )


def test_change_simulation_propagates_new_gap_deadline_and_commercial_recheck():
    result = simulate_tender_change(_change_request())

    assert result.before.direct_route_status == "FEASIBLE"
    assert result.simulated_after.direct_route_status == "RECOVERABLE"
    assert result.before.mandatory_gap_count == 0
    assert result.simulated_after.mandatory_gap_count == 1
    assert result.control_changes[0].id == "CTRL-CONTINUITY"
    assert result.control_changes[0].change_type == "NEW_CONTROL"
    assert result.control_changes[0].check.remediation is not None
    assert result.milestone_changes[0].change_type == "REPLACED"
    assert result.milestone_changes[0].previous_starts_at == "2026-09-18T12:00"
    assert result.milestone_changes[0].simulated_starts_at == "2026-09-20T12:00"
    assert result.commercial_recheck.status == "REVALIDATE"
    assert set(result.commercial_recheck.triggers) >= {"demand volume", "delivery scope"}
    assert result.clarification_questions[0].issue == "Demand volume is not measurable"
    assert any("Pricing scenarios" in item for item in result.invalidated_outputs)
    assert any("award values" in item for item in result.invalidated_outputs)
    assert result.trace[-1].id == "CHANGE-REPLAN"
    assert "stateless rehearsal" in result.boundaries[0]


def test_change_without_configured_signals_stays_reviewable_without_inventing_delta():
    request = ChangeSimulationRequest(
        tender=_baseline(),
        source_label="Administrative note.txt",
        amendment_text=(
            "[Page 1]\nPlease use the updated document title shown in the cover sheet. "
            "All remaining instructions continue to apply."
        ),
    )

    result = simulate_tender_change(request)

    assert result.control_changes == []
    assert result.milestone_changes == []
    assert result.clarification_questions == []
    assert result.commercial_recheck.status == "NO_AUTOMATIC_CHANGE"
    assert result.before == result.simulated_after
    assert result.recovery_actions[-1].startswith("A bid owner reviews")


def test_restated_optional_control_becomes_a_mandatory_gap_in_after_snapshot():
    baseline = _baseline().model_copy(
        update={
            "tender_text": (
                "[Page 1]\nThe supplier may maintain a disaster recovery capability. "
                "Tender submission closes on 18 September 2026 at 12:00 SGT."
            )
        }
    )
    request = ChangeSimulationRequest(
        tender=baseline,
        source_label="Corrigendum 4.pdf",
        amendment_text=(
            "[Page 2]\nThe supplier must maintain a disaster recovery capability with a "
            "four-hour recovery time objective."
        ),
    )

    result = simulate_tender_change(request)

    assert result.before.mandatory_gap_count == 0
    assert result.simulated_after.mandatory_gap_count == 1
    assert result.simulated_after.direct_route_status == "RECOVERABLE"
    assert result.control_changes[0].change_type == "RESTATED_CONTROL"
    assert result.control_changes[0].check.risk == "MANDATORY"


def test_unrelated_generic_milestone_is_added_without_deleting_mobilisation():
    baseline = _baseline().model_copy(
        update={
            "tender_text": (
                "[Page 1]\nMobilisation begins on 15 September 2026 at 09:00 SGT. "
                "Tender submission closes on 18 September 2026 at 12:00 SGT."
            )
        }
    )
    request = ChangeSimulationRequest(
        tender=baseline,
        source_label="Corrigendum 5.pdf",
        amendment_text=(
            "[Page 3]\nWarranty evidence is due on 30 September 2026 at 17:00 SGT."
        ),
    )

    result = simulate_tender_change(request)

    assert result.milestone_changes[0].change_type == "ADDED"
    assert result.milestone_changes[0].previous_starts_at is None
    assert result.before.next_milestone == "2026-09-15T09:00"
    assert result.simulated_after.next_milestone == "2026-09-15T09:00"


def test_negated_or_unchanged_commercial_wording_does_not_invalidate_outputs():
    request = ChangeSimulationRequest(
        tender=_baseline(),
        source_label="Administrative note.txt",
        amendment_text=(
            "[Page 1]\nThe supplier must demonstrate five years of relevant project "
            "experience. There is no additional scope, and service availability remains "
            "unchanged. The service adds no new locations."
        ),
    )

    result = simulate_tender_change(request)

    assert result.commercial_recheck.status == "NO_AUTOMATIC_CHANGE"
    assert result.commercial_recheck.triggers == []
    assert not any("Pricing" in item for item in result.invalidated_outputs)


def test_commercial_change_without_baseline_pricing_does_not_claim_pricing_was_stale():
    baseline = _baseline().model_copy(update={"pricing": None})
    request = ChangeSimulationRequest(
        tender=baseline,
        source_label="Corrigendum 6.pdf",
        amendment_text="[Page 1]\nThe service adds three new delivery locations.",
    )

    result = simulate_tender_change(request)

    assert result.commercial_recheck.status == "REVALIDATE"
    assert "delivery scope" in result.commercial_recheck.triggers
    assert not any("Pricing" in item for item in result.invalidated_outputs)
    assert not any("award" in item.casefold() for item in result.invalidated_outputs)
    assert "No baseline pricing output" in result.commercial_recheck.impact


def test_change_simulation_endpoint_is_non_persisting():
    with TestClient(app) as client:
        before = client.get("/api/bids/BID-DEMO-001").json()
        response = client.post(
            "/api/tender-lab/simulate-change",
            json=_change_request().model_dump(),
        )
        after = client.get("/api/bids/BID-DEMO-001").json()

    assert response.status_code == 200, response.text
    assert response.json()["simulated_after"]["direct_route_status"] == "RECOVERABLE"
    assert before == after
