"""Export deterministic API snapshots used by the GitHub Pages visual preview."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402


OUTPUT = ROOT / "frontend" / "public" / "static-demo"
CLEAR_AMENDMENT = (
    "R17 / Clause 4.3 is amended. Replace ‘not fewer than three personnel holding "
    "valid CISSP certification’ with ‘not fewer than four personnel holding valid "
    "CISSP certification’. All other clauses remain unchanged."
)
CHANGE_SAMPLE = """[Page 2]
The supplier must maintain disaster recovery with a four-hour recovery time objective.
The service adds three locations, but expected event volume remains TBC.
Tender submission closes on 20 September 2026 at 12:00 SGT."""


def save(name: str, payload: Any) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def expect(response: Any) -> Any:
    response.raise_for_status()
    return response.json()


def main() -> None:
    with TestClient(app) as client:
        main_bid = expect(client.post("/api/demo/reset"))
        fixtures = expect(client.get("/api/demo/fixtures"))
        save("bid-main.json", main_bid)
        save("fixtures.json", fixtures)

        for fixture in fixtures:
            fixture_id = fixture["id"]
            save(
                f"fixture-{fixture_id}.json",
                expect(client.post(f"/api/demo/fixtures/{fixture_id}")),
            )

        main_bid = expect(client.post("/api/demo/reset"))
        sme = expect(client.get("/api/tender-lab/sample/sme"))
        startup = expect(client.get("/api/tender-lab/sample/startup"))
        save("tender-sme.json", sme)
        save("tender-startup.json", startup)
        save("analysis-sme.json", expect(client.post("/api/tender-lab/analyze", json=sme)))
        save(
            "analysis-startup.json",
            expect(client.post("/api/tender-lab/analyze", json=startup)),
        )

        awards = expect(client.get("/api/public-data/gebiz/awards?query=cybersecurity"))
        save("award-context.json", awards)
        save(
            "partner-route.json",
            expect(
                client.post(
                    "/api/tender-lab/partner-route",
                    json={"tender": sme, "award_context": awards},
                )
            ),
        )
        save(
            "change-simulation.json",
            expect(
                client.post(
                    "/api/tender-lab/simulate-change",
                    json={
                        "tender": sme,
                        "source_label": "Corrigendum 3.pdf",
                        "amendment_text": CHANGE_SAMPLE,
                    },
                )
            ),
        )
        save(
            "agent-loop.json",
            expect(
                client.post(
                    "/api/tender-lab/agent-loop",
                    json={"tender": sme, "max_revision_rounds": 1},
                )
            ),
        )
        save(
            "proposal-plan.json",
            expect(client.post("/api/tender-lab/proposal/plan", json={"tender": startup})),
        )
        save(
            "proposal-review.json",
            expect(
                client.post(
                    "/api/tender-lab/proposal/review-answer",
                    json={
                        "tender": startup,
                        "question_id": "Q-SOLUTION",
                        "answer": "Our platform turns tender requirements into a traceable action plan.",
                    },
                )
            ),
        )
        save(
            "proposal-draft.json",
            expect(client.post("/api/tender-lab/proposal/draft", json={"tender": startup})),
        )

        r17 = next(item for item in main_bid["requirements"] if item["stable_key"] == "R17")
        preview = expect(
            client.post(
                "/api/bids/BID-DEMO-001/amendments/preview",
                json={
                    "requirement_id": r17["id"],
                    "source": {
                        "document_name": "DGA_ICT_2026_017_Corrigendum_2.pdf",
                        "document_version": 2,
                        "page": 2,
                        "section": "1. Amendment to Clause 4.3",
                        "text": CLEAR_AMENDMENT,
                    },
                },
            )
        )
        save("amendment-preview.json", preview)
        save(
            "amendment-applied.json",
            expect(
                client.post(
                    "/api/bids/BID-DEMO-001/amendments/apply",
                    json={
                        "preview_id": preview["preview_id"],
                        "reviewed_source_and_diff": True,
                        "confirmed_by": "Bid owner",
                    },
                )
            ),
        )
        client.post("/api/demo/reset").raise_for_status()


if __name__ == "__main__":
    main()
