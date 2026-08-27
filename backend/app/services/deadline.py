from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.enums import DeadlineRisk, TaskStatus
from app.models import Task, Tender
from app.services.clock import now


def deadline_risk_trace(session: Session, tender: Tender) -> dict[str, Any]:
    open_tasks = session.scalars(
        select(Task).where(
            Task.tender_id == tender.id,
            Task.status.in_(
                [TaskStatus.OPEN.value, TaskStatus.IN_PROGRESS.value, TaskStatus.WAITING.value]
            ),
        )
    ).all()
    calculated_at = now()
    if not open_tasks:
        return {
            "risk": DeadlineRisk.LOW.value,
            "calculated_at": calculated_at,
            "driver_task_id": None,
            "driver_task_title": None,
            "minimum_slack_hours": None,
            "tasks": [],
            "formula": "slack = (latest_safe_at or due_at) - estimated_duration - calculated_at",
            "thresholds": {
                "LOW": "> 48h",
                "MEDIUM": "12h < slack ≤ 48h",
                "HIGH": "0h ≤ slack ≤ 12h",
                "MISSED": "< 0h",
            },
        }

    task_traces = []
    for task in open_tasks:
        latest_finish = task.latest_safe_at or task.due_at
        latest_start = latest_finish - timedelta(hours=task.estimated_duration_hours)
        slack_hours = (latest_start - calculated_at).total_seconds() / 3600
        task_traces.append(
            {
                "task_id": task.id,
                "title": task.title,
                "status": task.status,
                "latest_finish": latest_finish,
                "latest_start": latest_start,
                "duration_hours": task.estimated_duration_hours,
                "slack_hours": round(slack_hours, 2),
            }
        )
    task_traces.sort(key=lambda item: item["slack_hours"])
    driver = task_traces[0]
    slack_hours = driver["slack_hours"]
    if slack_hours < 0:
        risk = DeadlineRisk.MISSED
    elif slack_hours <= 12:
        risk = DeadlineRisk.HIGH
    elif slack_hours <= 48:
        risk = DeadlineRisk.MEDIUM
    else:
        risk = DeadlineRisk.LOW
    return {
        "risk": risk.value,
        "calculated_at": calculated_at,
        "driver_task_id": driver["task_id"],
        "driver_task_title": driver["title"],
        "minimum_slack_hours": slack_hours,
        "tasks": task_traces,
        "formula": "slack = (latest_safe_at or due_at) - estimated_duration - calculated_at; the smallest open-task slack drives the headline risk.",
        "thresholds": {
            "LOW": "> 48h",
            "MEDIUM": "12h < slack ≤ 48h",
            "HIGH": "0h ≤ slack ≤ 12h",
            "MISSED": "< 0h",
        },
    }


def calculate_deadline_risk(session: Session, tender: Tender) -> DeadlineRisk:
    return DeadlineRisk(deadline_risk_trace(session, tender)["risk"])
