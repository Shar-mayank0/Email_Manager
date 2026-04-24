from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.api.dependencies import get_db
from backend.config.constants import STATUS_PENDING_REVIEW
from backend.core.policy.override_manager import (
	apply_override,
	mark_always_important,
	mark_always_promotional,
)
from backend.db.repository import email_repo


router = APIRouter()


class FeedbackRequest(BaseModel):
	gmail_id: str
	correct_category: str
	notes: str | None = None


class FeedbackResponse(BaseModel):
	gmail_id: str
	predicted: str
	actual: str
	confidence: float
	timestamp: datetime


class AlwaysImportantRequest(BaseModel):
	sender_email: str


class AlwaysPromotionalRequest(BaseModel):
	sender_domain: str


@router.post("", response_model=FeedbackResponse)
def submit_feedback(payload: FeedbackRequest, db: Session = Depends(get_db)) -> FeedbackResponse:
	_ensure_feedback_table(db)

	email = email_repo.get_email_by_gmail_id(db, payload.gmail_id)
	if email is None:
		raise HTTPException(status_code=404, detail="Email not found")

	editable_email = cast(Any, email)
	predicted = str(editable_email.category or "").strip().upper()
	actual = str(payload.correct_category or "").strip().upper()
	if not actual:
		raise HTTPException(status_code=400, detail="correct_category is required")

	confidence = _to_float(editable_email.confidence)
	timestamp = datetime.utcnow()

	apply_override(
		db=db,
		gmail_id=str(payload.gmail_id),
		new_category=actual,
		new_status=STATUS_PENDING_REVIEW,
	)

	db.execute(
		text(
			"""
			INSERT INTO feedback (
				gmail_id,
				predicted,
				actual,
				confidence,
				notes,
				timestamp
			)
			VALUES (
				:gmail_id,
				:predicted,
				:actual,
				:confidence,
				:notes,
				:timestamp
			)
			"""
		),
		{
			"gmail_id": str(payload.gmail_id),
			"predicted": predicted,
			"actual": actual,
			"confidence": confidence,
			"notes": str(payload.notes or "").strip(),
			"timestamp": timestamp,
		},
	)
	db.commit()

	return FeedbackResponse(
		gmail_id=str(payload.gmail_id),
		predicted=predicted,
		actual=actual,
		confidence=confidence,
		timestamp=timestamp,
	)


@router.post("/always-important")
def set_always_important(
	payload: AlwaysImportantRequest,
	db: Session = Depends(get_db),
) -> dict[str, Any]:
	try:
		return mark_always_important(db, payload.sender_email)
	except ValueError as exc:
		raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/always-promotional")
def set_always_promotional(
	payload: AlwaysPromotionalRequest,
	db: Session = Depends(get_db),
) -> dict[str, Any]:
	try:
		return mark_always_promotional(db, payload.sender_domain)
	except ValueError as exc:
		raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("")
def list_feedback(
	limit: int = Query(default=50, ge=1, le=500),
	offset: int = Query(default=0, ge=0),
	db: Session = Depends(get_db),
) -> dict[str, Any]:
	_ensure_feedback_table(db)
	rows = db.execute(
		text(
			"""
			SELECT id, gmail_id, predicted, actual, confidence, notes, timestamp
			FROM feedback
			ORDER BY timestamp DESC, id DESC
			LIMIT :limit OFFSET :offset
			"""
		),
		{"limit": limit, "offset": offset},
	).mappings().all()

	items: list[dict[str, Any]] = []
	for row in rows:
		items.append(
			{
				"id": int(row.get("id") or 0),
				"gmail_id": str(row.get("gmail_id") or ""),
				"predicted": str(row.get("predicted") or ""),
				"actual": str(row.get("actual") or ""),
				"confidence": _to_float(row.get("confidence")),
				"notes": str(row.get("notes") or ""),
				"timestamp": row.get("timestamp"),
			}
		)

	return {"items": items, "limit": limit, "offset": offset}


def _ensure_feedback_table(db: Session) -> None:
	db.execute(
		text(
			"""
			CREATE TABLE IF NOT EXISTS feedback (
				id INTEGER PRIMARY KEY AUTOINCREMENT,
				gmail_id TEXT NOT NULL,
				predicted TEXT NOT NULL,
				actual TEXT NOT NULL,
				confidence REAL NOT NULL DEFAULT 0,
				notes TEXT,
				timestamp DATETIME NOT NULL
			)
			"""
		)
	)
	db.commit()


def _to_float(value: Any) -> float:
	try:
		return float(value)
	except (TypeError, ValueError):
		return 0.0
